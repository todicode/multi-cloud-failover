# Giai đoạn 6 — DNS và HTTPS

## 1. Mục tiêu và đầu ra

Cấu hình đường truy cập có hostname và HTTPS cho ứng dụng đã nghiệm thu ở [giai đoạn 5](giaidoan5_k3s_va_trien_khai_workload.md). Project sử dụng nhánh DNS riêng mcf.todicode.tech thuộc tên miền todicode.tech.

| Hostname | Vai trò |
|---|---|
| aws.mcf.todicode.tech | Origin ứng dụng AWS |
| azure.mcf.todicode.tech | Origin ứng dụng Azure |
| app.mcf.todicode.tech | Địa chỉ ứng dụng chung, chuẩn bị cho DNS failover |

Route 53 quản lý public hosted zone mcf.todicode.tech. DNS gốc todicode.tech cấu hình bản ghi NS để delegate nhánh mcf tới nameserver của hosted zone. Các certificate, Ingress HTTPS và health check writer được bổ sung theo từng bước thực hành.

## 2. Trạng thái bắt đầu

- Hai ứng dụng chạy cùng image digest ứng với commit c56fd3f trên hai K3s độc lập.
- AWS là PostgreSQL primary, Azure là standby, WAL streaming và dữ liệu nghiệp vụ đã được đối chiếu.
- HTTP qua Traefik đã được kiểm tra trên Public IP của hai cloud.
- Form trình duyệt hiện dùng SSH forwarding tới loopback để đáp ứng yêu cầu secure context của crypto.randomUUID.
- Tên miền do người thực hành cung cấp là todicode.tech.

Kết quả tra cứu DNS ngày 2026-11-13 cho thấy NS của todicode.tech là tech-domains.earth.orderbox-dns.com, tech-domains.mercury.orderbox-dns.com, tech-domains.venus.orderbox-dns.com và tech-domains.mars.orderbox-dns.com. Tra cứu public DNS tại thời điểm kiểm tra trả NXDOMAIN cho nhánh mcf.todicode.tech và ba hostname dự kiến. AWS CLI với profile default trả danh sách trống cho public hosted zone todicode.tech và mcf.todicode.tech.

## 3. Tổ chức subdomain cho nhiều project

Một tên miền có thể chứa nhiều nhánh subdomain, mỗi nhánh phục vụ một project. Project này dùng mcf.todicode.tech làm namespace DNS. Ví dụ project khác có thể dùng portfolio.todicode.tech hoặc một nhánh theo tên project.

Luồng phân quyền DNS dự kiến của đồ án.

```text
todicode.tech — DNS gốc tại nhà cung cấp hiện tại
    └── NS mcf.todicode.tech → nameserver hosted zone Route 53
            ├── aws.mcf.todicode.tech → Public IP AWS
            ├── azure.mcf.todicode.tech → Public IP Azure
            └── app.mcf.todicode.tech → đường truy cập chung
```

Hosted zone lưu các record mà Route 53 chịu trách nhiệm trả lời. Record NS tại DNS gốc chỉ định nameserver có thẩm quyền cho nhánh mcf. Khi tạo hosted zone, Route 53 cấp các nameserver để dùng ở bước delegation. Mỗi hostname origin sau đó được ánh xạ tới Public IP tương ứng của ứng dụng.

## 4. Chuẩn bị Terraform root module DNS

Terraform DNS đặt tại deploy/terraform/dns trong cùng repository. Root module DNS có state riêng để quản lý vòng đời hosted zone và record. Hai root module compute hiện tại tiếp tục nằm tại deploy/terraform/aws và deploy/terraform/azure.

Trong Git Bash trên laptop tại thư mục gốc repository, tạo thư mục DNS và tái sử dụng khai báo phiên bản cùng provider lock file AWS hiện tại.

```bash
cd /d/multi-cloud-failover
mkdir -p deploy/terraform/dns
cp deploy/terraform/aws/versions.tf deploy/terraform/dns/versions.tf
cp deploy/terraform/aws/.terraform.lock.hcl deploy/terraform/dns/.terraform.lock.hcl
```

versions.tf khai báo Terraform >= 1.10.0 và < 2.0.0 cùng AWS provider ~> 6.0. Lock file giữ phiên bản provider và checksum đã chọn trong root AWS. File providers.tf và resource hosted zone được viết ở bước tiếp theo trước khi init/validate/plan.

Kiểm tra file đã copy.

```bash
cat deploy/terraform/dns/versions.tf
git status --short
```

Mong đợi versions.tf có khối terraform và required_providers giống file AWS của chính repository. Các file Terraform được người thực hành tạo từng bước; hướng dẫn này được mở rộng theo tiến độ thực hành.

### 4.1. Xác nhận AWS profile và cấu hình provider

Trước khi cấu hình DNS, kiểm tra danh tính của profile dùng cho project trong Git Bash.

```bash
aws sts get-caller-identity --profile default --no-cli-pager
```

Đối chiếu Account và Arn với tài khoản quản lý EC2 của project. Tại checkpoint ngày 2026-11-13, profile default đăng nhập bằng IAM user todicode và sở hữu EC2 mcf-aws-primary. Tên profile là tên cấu hình trên laptop. Mỗi profile có thể sử dụng credential của một tài khoản AWS khác nhau.

Sau khi chuẩn bị thư mục và hai file ở mục 4, tạo file deploy/terraform/dns/providers.tf với nội dung sau.

```hcl
provider "aws" {
  region  = "ap-southeast-1"
  profile = "default"
}
```

profile default chọn cấu hình AWS CLI đã dùng cho hạ tầng AWS của project. region ap-southeast-1 là region mặc định của provider trong root module này. Route 53 public DNS sử dụng endpoint toàn cục, hosted zone quản lý tên miền độc lập với vị trí VM AWS/Azure.

### 4.2. Khởi tạo và kiểm tra cấu hình Terraform DNS

Trong Git Bash trên laptop tại thư mục gốc repository, chạy lần lượt các lệnh sau.

```bash
terraform -chdir=deploy/terraform/dns fmt
terraform -chdir=deploy/terraform/dns init
terraform -chdir=deploy/terraform/dns validate
```

fmt chuẩn hóa định dạng file Terraform. init chuẩn bị working directory và cài AWS provider theo dependency lock file. validate kiểm tra cú pháp, schema và tính nhất quán của cấu hình đã khai báo. Hai thông báo mong đợi là Terraform has been successfully initialized! và Success! The configuration is valid.

Checkpoint này xác nhận root module DNS sẵn sàng để bổ sung resource hosted zone. Thao tác tạo hosted zone sẽ được thực hiện bằng plan/apply sau khi viết resource ở bước tiếp theo.

### 4.3. Khai báo public hosted zone và xem plan

Tạo file deploy/terraform/dns/hosted-zone.tf với nội dung sau.

```hcl
resource "aws_route53_zone" "project" {
  name    = "mcf.todicode.tech"
  comment = "DNS for the multi-cloud failover project"

  tags = {
    Name    = "mcf-dns"
    Project = "multi-cloud-failover"
  }
}
```

aws_route53_zone là loại resource quản lý hosted zone. project là tên resource trong Terraform, tạo địa chỉ aws_route53_zone.project. name là nhánh DNS mà hosted zone quản lý. comment mô tả mục đích, tags giúp nhận diện tài nguyên trong tài khoản AWS.

Resource này khai báo public hosted zone theo cấu hình public zone của provider. Khi được tạo, zone sẽ có các record NS và SOA mặc định. Thuộc tính name_servers của resource cung cấp danh sách nameserver để cấu hình delegation tại DNS gốc ở bước sau.

Trong Git Bash tại thư mục gốc repository, chạy lần lượt.

```bash
terraform -chdir=deploy/terraform/dns fmt
terraform -chdir=deploy/terraform/dns validate
terraform -chdir=deploy/terraform/dns plan
```

Plan mong đợi tại checkpoint này.

```text
# aws_route53_zone.project will be created
Plan: 1 to add, 0 to change, 0 to destroy.
```

name cần hiển thị mcf.todicode.tech. Các thuộc tính zone_id và name_servers sẽ hiển thị known after apply vì AWS cấp chúng khi tạo zone. plan xem trước thay đổi. Checkpoint này hoàn thành khi đối chiếu được plan, bước apply và lấy nameserver sẽ được bổ sung tiếp theo.

### 4.4. Khai báo output, tạo hosted zone và lấy nameserver

Tạo file deploy/terraform/dns/output.tf để hiển thị ID và danh sách nameserver của hosted zone sau khi apply.

```hcl
output "dns_zone_id" {
  description = "Route 53 hosted zone ID for the project"
  value       = aws_route53_zone.project.zone_id
}

output "dns_name_servers" {
  description = "Authoritative nameservers for mcf.todicode.tech"
  value       = aws_route53_zone.project.name_servers
}
```

dns_zone_id là ID dùng khi tạo DNS record trong zone. dns_name_servers là danh sách nameserver mà Route 53 cấp cho zone, dùng để cấu hình NS delegation tại DNS gốc todicode.tech. output đọc các thuộc tính của resource sau khi AWS tạo xong và hiển thị chúng cho người vận hành.

Trong Git Bash tại thư mục gốc repository, chạy lần lượt.

```bash
terraform -chdir=deploy/terraform/dns fmt
terraform -chdir=deploy/terraform/dns validate
terraform -chdir=deploy/terraform/dns apply
```

apply sẽ tính lại plan và hiển thị prompt xác nhận. Đối chiếu tên zone mcf.todicode.tech và Plan: 1 to add, 0 to change, 0 to destroy. Nhập yes để tạo hosted zone trong tài khoản AWS của provider default.

Kết quả mong đợi là Apply complete! Resources: 1 added, 0 changed, 0 destroyed. Phần Outputs hiển thị dns_zone_id và bốn nameserver trong dns_name_servers. Xem lại các giá trị bằng lệnh sau.

```bash
terraform -chdir=deploy/terraform/dns output
```

Tại checkpoint này, hosted zone đã sẵn sàng để cấu hình delegation. Bước tiếp theo sử dụng đủ bốn nameserver vừa được AWS cấp để tạo record NS cho nhánh mcf tại DNS gốc todicode.tech.

Phí hosted zone hiện là 0,50 USD/zone/tháng cho 25 zone đầu tiên, cùng phí truy vấn DNS theo mức sử dụng. Phí tháng của hosted zone được tính nguyên tháng. [Bảng giá Route 53](https://aws.amazon.com/route53/pricing/).

### 4.5. Delegate nhánh mcf tại DNS gốc

Checkpoint tạo zone ngày 2026-11-13 đã được đối chiếu với AWS API. Hosted zone mcf.todicode.tech là public zone, ID Z043946815CRXHICLXRTS. DNS gốc todicode.tech hiện dùng các nameserver Orderbox. Public DNS cho nhánh mcf tại checkpoint này trả NXDOMAIN, nên cần cấu hình delegation.

Đăng nhập trang quản lý tên miền, chọn todicode.tech và mở mục quản lý bản ghi DNS, thường có tên DNS Management, Manage DNS hoặc DNS Records. Tại zone todicode.tech, thêm các bản ghi NS có Host/Name là mcf.

| Type | Host/Name | Value/Target | TTL |
|---|---|---|---|
| NS | mcf | ns-1064.awsdns-05.org | 300 |
| NS | mcf | ns-1656.awsdns-15.co.uk | 300 |
| NS | mcf | ns-246.awsdns-30.com | 300 |
| NS | mcf | ns-901.awsdns-48.net | 300 |

Bảng này sử dụng bốn nameserver từ Terraform output của hosted zone hiện tại. Khi tạo lại hosted zone, đối chiếu dns_name_servers và sử dụng bộ giá trị AWS cấp cho zone mới.

Một số giao diện cho nhập nhiều value trong cùng record NS. Với giao diện đó, dùng một record có Host mcf và thêm đủ bốn value. Nếu giao diện yêu cầu hostname đầy đủ trong ô Name, nhập mcf.todicode.tech. Nếu TTL 300 nằm ngoài lựa chọn của nhà cung cấp, dùng TTL mặc định của giao diện.

NS delegation giao quyền trả lời DNS cho nhánh mcf.todicode.tech tới bốn nameserver Route 53. Các record cho aws.mcf.todicode.tech, azure.mcf.todicode.tech và app.mcf.todicode.tech sẽ được khai báo trong hosted zone này.

Sau khi lưu, kiểm tra từ Git Bash trên laptop.

```bash
nslookup -type=NS mcf.todicode.tech 1.1.1.1
nslookup -type=NS mcf.todicode.tech 8.8.8.8
```

Kết quả mong đợi liệt kê đủ bốn nameserver của Route 53 trong bảng trên. Thứ tự có thể khác nhau. Nếu resolver còn trả NXDOMAIN sau khi vừa lưu, đợi cache DNS hết hạn rồi kiểm tra lại. Checkpoint delegation hoàn tất khi public DNS trả đúng bộ nameserver của hosted zone.

Kết quả thực hành đã xác nhận cả 1.1.1.1 và 8.8.8.8 trả đủ bốn nameserver của hosted zone. Checkpoint delegation đã hoàn tất.

### 4.6. Chuẩn bị biến IP cho hai origin

Hai origin sử dụng hostname aws.mcf.todicode.tech và azure.mcf.todicode.tech. Chuẩn bị input variable để cung cấp địa chỉ IPv4 public của từng cloud cho các record A ở bước tiếp theo.

Tạo file deploy/terraform/dns/variables.tf.

```hcl
variable "aws_public_ip" {
  description = "Public IPv4 address of the AWS origin"
  type        = string
}

variable "azure_public_ip" {
  description = "Public IPv4 address of the Azure origin"
  type        = string
}
```

Các block variable khai báo tên và kiểu dữ liệu đầu vào. Trong resource, dùng var.aws_public_ip và var.azure_public_ip để đọc các giá trị này. Tạo file deploy/terraform/dns/terraform.tfvars và điền giá trị theo output của hai root module compute. Địa chỉ tại checkpoint hiện tại như sau.

```hcl
aws_public_ip   = "175.41.152.242"
azure_public_ip = "4.145.30.250"
```

Terraform tự đọc terraform.tfvars trong thư mục root module đang chạy. File này được gitignore hiện tại của repository loại trừ. Khi hạ tầng được tạo lại, lấy output aws_public_ip của deploy/terraform/aws và azure_public_ip của deploy/terraform/azure để cập nhật các giá trị.

Trong Git Bash tại thư mục gốc repository, kiểm tra cấu hình.

```bash
terraform -chdir=deploy/terraform/dns fmt
terraform -chdir=deploy/terraform/dns validate
git check-ignore deploy/terraform/dns/terraform.tfvars
```

Mong đợi validate trả Success! The configuration is valid. và check-ignore trả đường dẫn deploy/terraform/dns/terraform.tfvars. Bước tiếp theo sẽ bổ sung các resource record A sử dụng hai biến này.

### 4.7. Khai báo hai record A cho origin và xem plan

Tạo file deploy/terraform/dns/records.tf với nội dung sau.

```hcl
resource "aws_route53_record" "aws_origin" {
  zone_id = aws_route53_zone.project.zone_id
  name    = "aws.${aws_route53_zone.project.name}"
  type    = "A"
  ttl     = 60
  records = [var.aws_public_ip]
}

resource "aws_route53_record" "azure_origin" {
  zone_id = aws_route53_zone.project.zone_id
  name    = "azure.${aws_route53_zone.project.name}"
  type    = "A"
  ttl     = 60
  records = [var.azure_public_ip]
}
```

aws_route53_record quản lý một DNS record trong hosted zone được chỉ định qua zone_id. Hai resource có địa chỉ Terraform aws_route53_record.aws_origin và aws_route53_record.azure_origin. Cú pháp ${...} chèn tên hosted zone vào chuỗi, tạo hostname aws.mcf.todicode.tech và azure.mcf.todicode.tech.

Record A ánh xạ hostname tới địa chỉ IPv4. records là danh sách giá trị, mỗi origin hiện có một IP từ terraform.tfvars. TTL 60 cho phép resolver cache bản ghi trong 60 giây. Cả hai record được quản lý tại hosted zone Route 53 mcf.todicode.tech.

Trong Git Bash tại thư mục gốc repository, chạy lần lượt.

```bash
terraform -chdir=deploy/terraform/dns fmt
terraform -chdir=deploy/terraform/dns validate
terraform -chdir=deploy/terraform/dns plan
```

Plan mong đợi liệt kê hai resource record sẽ được tạo.

```text
# aws_route53_record.aws_origin will be created
# aws_route53_record.azure_origin will be created
Plan: 2 to add, 0 to change, 0 to destroy.
```

Đối chiếu hostname, type A, TTL 60 và records. Giá trị IP tại checkpoint này là 175.41.152.242 cho aws.mcf.todicode.tech và 4.145.30.250 cho azure.mcf.todicode.tech. Bước tiếp theo sẽ apply hai record và kiểm tra DNS cùng HTTP theo hostname.

### 4.8. Apply hai origin record và kiểm tra phân giải DNS

Sau khi đối chiếu plan ở mục 4.7, chạy trong Git Bash tại thư mục gốc repository.

```bash
terraform -chdir=deploy/terraform/dns apply
```

Terraform tính lại plan. Kiểm tra hai resource aws_route53_record.aws_origin và aws_route53_record.azure_origin có đúng hostname, IP và TTL 60. Khi plan hiển thị 2 to add, 0 to change, 0 to destroy, nhập yes.

Kết quả mong đợi.

```text
Apply complete! Resources: 2 added, 0 changed, 0 destroyed.
```

Sau khi apply hoàn tất, kiểm tra record A thông qua public DNS.

```bash
nslookup -type=A aws.mcf.todicode.tech 1.1.1.1
nslookup -type=A azure.mcf.todicode.tech 1.1.1.1
```

Đối chiếu địa chỉ trong phần câu trả lời của từng hostname.

| Hostname | Địa chỉ IPv4 tại checkpoint |
|---|---|
| aws.mcf.todicode.tech | 175.41.152.242 |
| azure.mcf.todicode.tech | 4.145.30.250 |

Nếu resolver còn cache kết quả trước khi tạo record, đợi cache hết hạn rồi kiểm tra lại. Có thể đối chiếu trực tiếp một nameserver authoritative của zone bằng các lệnh sau.

```bash
nslookup -type=A aws.mcf.todicode.tech ns-1064.awsdns-05.org
nslookup -type=A azure.mcf.todicode.tech ns-1064.awsdns-05.org
```

Nameserver trong hai lệnh trên thuộc hosted zone hiện tại. Khi tạo lại zone, dùng một nameserver từ dns_name_servers của zone mới. Checkpoint này hoàn tất khi cả hai hostname phân giải về đúng IP origin qua public resolver. Bước tiếp theo kiểm tra HTTP qua hostname và chuẩn bị HTTPS.

Kết quả thực hành ngày 2026-11-14 đã xác nhận public resolver 1.1.1.1 trả aws.mcf.todicode.tech về 175.41.152.242 và azure.mcf.todicode.tech về 4.145.30.250.

### 4.9. Kiểm tra HTTP qua hostname của hai origin

Trong Git Bash trên laptop, kiểm tra ứng dụng của từng cloud thông qua hostname.

```bash
curl -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  http://aws.mcf.todicode.tech/version

curl -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  http://azure.mcf.todicode.tech/version
```

Cả hai request cần trả HTTP 200, version v0.1.0 và commit_sha c56fd3f30baee50fa779607dc0fb1a2133b53a9d. environment lần lượt là aws và azure, region lần lượt là ap-southeast-1 và southeastasia.

Tiếp theo kiểm tra writer health của database phía sau từng ứng dụng.

```bash
curl -sS --max-time 10 -w '\nHTTP %{http_code}\n' \
  http://aws.mcf.todicode.tech/health/database

curl -sS --max-time 10 -w '\nHTTP %{http_code}\n' \
  http://azure.mcf.todicode.tech/health/database
```

Lệnh writer health dùng -sS để in được response body cùng mã HTTP 503 của standby. Đầu ra mong đợi tại checkpoint này.

| Origin | /version | /health/database | Vai trò database |
|---|---|---|---|
| AWS | 200 | 200 | primary, writable true |
| Azure | 200 | 503 | standby, writable false, replication_connected true |

Ingress issues-app hiện dùng ingressClassName traefik và rule đường dẫn / cho mọi hostname. Request HTTP qua hai hostname mới đã được kiểm tra thành công ngày 2026-11-14, với đúng environment, image commit và vai trò database trong bảng trên.

Checkpoint này xác nhận kết nối từ laptop qua hostname, Traefik, Service ứng dụng và database của từng cloud. Bước tiếp theo cấu hình certificate và Ingress HTTPS cho các hostname.

### 4.10. Cài Certbot và plugin Route 53 trên AWS

HTTPS sử dụng certificate do Let's Encrypt cấp. Certbot chạy trên host để xin và gia hạn certificate, với plugin dns-route53 thực hiện xác minh DNS-01. Khi xin certificate cho một hostname, plugin tạo TXT record dưới _acme-challenge của hostname đó, chờ xác minh từ Let's Encrypt rồi dọn record challenge.

Certificate và private key được đưa vào Kubernetes TLS Secret ở bước cấu hình Ingress. Traefik sử dụng Secret này để phục vụ HTTPS cho các hostname được khai báo. Quyền gọi Route 53 API và cấu hình tự động gia hạn sẽ được bổ sung theo từng checkpoint tiếp theo.

Trong Git Bash trên laptop, SSH vào máy AWS.

```bash
ssh -i ~/.ssh/mcf-lab ubuntu@175.41.152.242
```

Tại terminal Ubuntu trên EC2, cài Certbot và plugin từ Ubuntu package repository.

```bash
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-dns-route53
```

certbot cung cấp ACME client để làm việc với Let's Encrypt. python3-certbot-dns-route53 bổ sung authenticator cập nhật record DNS qua Route 53 API. Hai package có sẵn cho Ubuntu 24.04 đang dùng trên EC2.

Kiểm tra công cụ sau khi cài.

```bash
certbot --version
sudo certbot plugins
```

Kết quả mong đợi là thông tin phiên bản Certbot và plugin dns-route53 trong danh sách, với chức năng Authenticator. Checkpoint này hoàn tất khi plugin được nhận diện. Bước tiếp theo cấu hình quyền Route 53 cho Certbot trên AWS.

#### 4.10.1. Xử lý SSH timeout khi IP của người vận hành thay đổi

Rule SSH trên AWS dùng var.admin_cidr để cho phép địa chỉ IPv4 public của người vận hành truy cập TCP 22. Khi mạng đang dùng được cấp IP public mới, cần cập nhật giá trị này trong deploy/terraform/aws/terraform.tfvars.

Nếu SSH đang chờ kết nối, nhấn Ctrl+C. Trong Git Bash trên laptop, xem IP public hiện tại.

```bash
curl -fsS https://checkip.amazonaws.com
```

Mở deploy/terraform/aws/terraform.tfvars và cập nhật dòng admin_cidr thành IP vừa lấy kèm /32. Ví dụ tại lần chẩn đoán ngày 2026-11-14, IP hiện tại là 171.251.235.11 trong khi rule SSH đang cho phép 171.251.233.105/32.

```hcl
admin_cidr = "171.251.235.11/32"
```

Chạy plan trong root module AWS để xem thay đổi.

```bash
terraform -chdir=deploy/terraform/aws plan
```

Plan đã đối chiếu tại lần chẩn đoán này là update in-place của aws_vpc_security_group_ingress_rule.ssh, chỉ thay cidr_ipv4, với 0 to add, 1 to change, 0 to destroy. Sau khi đối chiếu plan, apply và nhập yes để cập nhật rule.

```bash
terraform -chdir=deploy/terraform/aws apply
```

Kết nối lại EC2.

```bash
ssh -o ConnectTimeout=10 -i ~/.ssh/mcf-lab ubuntu@175.41.152.242
```

Tại lần chẩn đoán này, EC2 vẫn running, cả hai status check ok và HTTP /health/live trả 200. Checkpoint khôi phục SSH hoàn tất khi người vận hành đăng nhập được vào Ubuntu và tiếp tục bước cài Certbot.

Đã cập nhật admin_cidr trong terraform.tfvars và apply thành công ngày 2026-11-14, với 0 added, 1 changed, 0 destroyed. AWS API xác nhận rule TCP 22 cho phép 171.251.235.11/32. Kiểm tra kết nối từ laptop đã nhận banner OpenSSH của Ubuntu trên cổng 22. Người vận hành tiếp tục đăng nhập bằng key mcf-lab để thực hiện bước cài Certbot.

### 4.11. Khai báo IAM role cho Certbot trên EC2

Certbot trên AWS sẽ sử dụng temporary credentials của IAM role gắn với EC2. Triển khai theo thứ tự role và trust policy, permissions policy cho DNS challenge, instance profile rồi gắn profile với EC2.

Trong checkpoint này, tạo file deploy/terraform/aws/iam.tf trên laptop và thêm resource sau.

```hcl
resource "aws_iam_role" "certbot" {
  name = "mcf-aws-certbot"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name    = "mcf-aws-certbot"
    Project = "multi-cloud-failover"
  }
}
```

assume_role_policy là trust policy của role. Principal Service ec2.amazonaws.com chỉ định EC2 là service được tin cậy để assume role. sts:AssumeRole là hành động được cho phép trong trust policy. jsonencode chuyển cấu trúc HCL thành chuỗi JSON mà IAM API sử dụng. Version 2012-10-17 là phiên bản ngôn ngữ policy của IAM.

Role sẽ nhận permissions policy cho Route 53 ở checkpoint tiếp theo, sau đó được đặt trong instance profile gắn với EC2. Khi hoàn thiện chuỗi cấu hình, Certbot chạy trên host sẽ dùng temporary credentials do EC2 cung cấp để thực hiện DNS challenge.

Chạy trong Git Bash trên laptop tại thư mục gốc repository.

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
terraform -chdir=deploy/terraform/aws plan
```

Plan mong đợi tại checkpoint này.

```text
# aws_iam_role.certbot will be created
Plan: 1 to add, 0 to change, 0 to destroy.
```

Đối chiếu tên role mcf-aws-certbot và Principal Service ec2.amazonaws.com. Checkpoint này dừng ở việc xem plan của role. Permissions policy và instance profile sẽ được bổ sung theo các bước thực hành tiếp theo.

### 4.12. Truyền hosted zone ID vào root module AWS

Policy cho Certbot cần ARN của hosted zone mcf.todicode.tech để giới hạn phạm vi cập nhật DNS. Root module DNS quản lý zone, còn root module AWS quản lý IAM role và EC2. Truyền ID của zone vào root module AWS qua input variable.

Thêm block sau vào cuối file deploy/terraform/aws/variables.tf.

```hcl
variable "dns_zone_id" {
  description = "Route 53 hosted zone ID used for certificate DNS validation"
  type        = string
}
```

Lệnh Terraform với -chdir=deploy/terraform/aws đọc khai báo trong root module AWS. Nếu gặp cảnh báo Value for undeclared variable cho dns_zone_id, kiểm tra đường dẫn file vừa sửa. Trường hợp block dns_zone_id được thêm vào deploy/terraform/dns/variables.tf, chuyển toàn bộ block đó sang deploy/terraform/aws/variables.tf. Hai biến aws_public_ip và azure_public_ip tiếp tục phục vụ các record ở root module DNS.

Xem ID hiện tại bằng lệnh sau trong Git Bash trên laptop.

```bash
terraform -chdir=deploy/terraform/dns output -raw dns_zone_id
```

Giá trị đã đối chiếu tại checkpoint này là Z043946815CRXHICLXRTS. Thêm dòng sau vào deploy/terraform/aws/terraform.tfvars.

```hcl
dns_zone_id = "Z043946815CRXHICLXRTS"
```

Biến này dùng trong policy dưới dạng var.dns_zone_id. ARN của hosted zone sẽ có dạng arn:aws:route53:::hostedzone/${var.dns_zone_id}. Khi zone được tạo lại, cập nhật input từ output mới của root module DNS.

Kiểm tra cấu hình root module AWS.

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
terraform -chdir=deploy/terraform/aws plan
```

Tại checkpoint này, plan tiếp tục hiển thị 1 to add, 0 to change, 0 to destroy cho IAM role đã khai báo ở mục 4.11. Input variable chuẩn bị phạm vi hosted zone cho policy ở bước thực hành kế tiếp.

### 4.13. Khai báo policy Route 53 cho role Certbot

Biến dns_zone_id đã được chuyển đúng sang root module AWS và validate thành công. Thêm resource sau vào cuối deploy/terraform/aws/iam.tf, sau block aws_iam_role.certbot.

```hcl
resource "aws_iam_role_policy" "certbot_route53" {
  name = "mcf-certbot-route53"
  role = aws_iam_role.certbot.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "route53:ListHostedZones"
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "route53:GetChange"
        Resource = "arn:aws:route53:::change/*"
      },
      {
        Effect   = "Allow"
        Action   = "route53:ChangeResourceRecordSets"
        Resource = "arn:aws:route53:::hostedzone/${var.dns_zone_id}"
        Condition = {
          "ForAllValues:StringEquals" = {
            "route53:ChangeResourceRecordSetsRecordTypes" = ["TXT"]
          }
          Null = {
            "route53:ChangeResourceRecordSetsRecordTypes" = "false"
          }
        }
      }
    ]
  })
}
```

aws_iam_role_policy quản lý inline policy gắn trực tiếp vào role được chọn qua thuộc tính role. Policy này có ba statement theo các API mà Certbot Route 53 plugin sử dụng.

- ListHostedZones cho phép plugin tìm hosted zone phụ trách hostname. API này dùng Resource * vì thao tác liệt kê thực hiện ở cấp tài khoản.
- GetChange cho phép đọc trạng thái thay đổi DNS để đợi đồng bộ. ARN change/* bao phủ các change ID được Route 53 sinh trong quá trình chạy.
- ChangeResourceRecordSets cho phép cập nhật record trong hosted zone được chỉ định bởi var.dns_zone_id. Điều kiện ForAllValues:StringEquals yêu cầu tất cả record trong request có type TXT. Null false yêu cầu context key loại record phải tồn tại.

Phạm vi ghi của policy là các record TXT trong hosted zone của project. Plugin dùng quyền này để đặt và dọn TXT challenge khi xin hoặc gia hạn certificate. Quyền của policy sẽ có hiệu lực cho ứng dụng trên EC2 sau bước gắn instance profile.

Trong Git Bash trên laptop tại thư mục gốc repository, chạy các lệnh sau.

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
terraform -chdir=deploy/terraform/aws plan
```

Plan mong đợi tại checkpoint này.

```text
# aws_iam_role.certbot will be created
# aws_iam_role_policy.certbot_route53 will be created
Plan: 2 to add, 0 to change, 0 to destroy.
```

Đối chiếu ARN hosted zone kết thúc bằng Z043946815CRXHICLXRTS và điều kiện record type TXT trong policy. Bước tiếp theo tạo instance profile và gắn role vào EC2 trước khi apply toàn bộ phần quyền Certbot.

### 4.14. Khai báo instance profile và gắn vào EC2

Instance profile chứa IAM role để EC2 cung cấp temporary credentials cho ứng dụng chạy trên host. Role Certbot được đặt vào profile này, sau đó aws_instance.primary tham chiếu tới profile qua iam_instance_profile.

Thêm resource sau vào cuối deploy/terraform/aws/iam.tf.

```hcl
resource "aws_iam_instance_profile" "certbot" {
  name = "mcf-aws-certbot"
  role = aws_iam_role.certbot.name

  tags = {
    Name    = "mcf-aws-certbot"
    Project = "multi-cloud-failover"
  }
}
```

Trong deploy/terraform/aws/compute.tf, tìm block resource aws_instance primary. Thêm thuộc tính sau vào trong block này, cùng cấp với ami, instance_type và key_name.

```hcl
iam_instance_profile = aws_iam_instance_profile.certbot.name
```

role trong instance profile chọn role mcf-aws-certbot. iam_instance_profile trong EC2 chọn tên profile vừa khai báo. Các tham chiếu này thiết lập quan hệ phụ thuộc để Terraform tạo role, tạo profile rồi gắn profile vào EC2.

Luồng cấp quyền khi cấu hình được áp dụng.

```text
EC2 → instance profile → IAM role → policy Route 53
Certbot trên host → temporary credentials của role → Route 53 API
```

Trong Git Bash trên laptop tại thư mục gốc repository, chạy các lệnh kiểm tra.

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
terraform -chdir=deploy/terraform/aws plan
```

Plan mong đợi tại checkpoint này.

```text
# aws_iam_role.certbot will be created
# aws_iam_role_policy.certbot_route53 will be created
# aws_iam_instance_profile.certbot will be created
# aws_instance.primary will be updated in-place
Plan: 3 to add, 1 to change, 0 to destroy.
```

Đối chiếu thay đổi trên EC2 là thuộc tính iam_instance_profile và hành động update in-place. Checkpoint này hoàn tất khi đối chiếu được plan. Bước tiếp theo apply phần quyền và kiểm tra role từ EC2.

### 4.15. Apply phần quyền và xác nhận role từ EC2

Plan đã được đối chiếu ở checkpoint 4.14, với ba resource IAM sẽ được tạo và EC2 được update in-place để gắn profile. Trong Git Bash trên laptop tại thư mục gốc repository, chạy lệnh sau.

```bash
terraform -chdir=deploy/terraform/aws apply
```

Đối chiếu plan 3 to add, 1 to change, 0 to destroy, sau đó nhập yes. Kết quả mong đợi.

```text
Apply complete! Resources: 3 added, 1 changed, 0 destroyed.
```

Sau khi apply hoàn tất, SSH vào EC2 từ Git Bash trên laptop.

```bash
ssh -o ConnectTimeout=10 -i ~/.ssh/mcf-lab ubuntu@175.41.152.242
```

Trong terminal Ubuntu trên EC2, lấy token IMDSv2 rồi truy vấn tên role được cung cấp qua instance metadata.

```bash
MCF_IMDS_TOKEN=$(curl -fsS --max-time 5 -X PUT \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 300' \
  http://169.254.169.254/latest/api/token)

curl -fsS --max-time 5 -w '\n' \
  -H "X-aws-ec2-metadata-token: $MCF_IMDS_TOKEN" \
  http://169.254.169.254/latest/meta-data/iam/security-credentials/
```

169.254.169.254 là endpoint instance metadata mà EC2 cung cấp bên trong máy. Request PUT tạo session token có hiệu lực 300 giây. Request GET sử dụng token để đọc tên IAM role. EC2 hiện yêu cầu IMDSv2 qua cấu hình http_tokens required trong Terraform.

Kết quả mong đợi.

```text
mcf-aws-certbot
```

Nếu metadata chưa hiển thị role ngay sau khi attach, đợi đồng bộ IAM rồi chạy lại hai lệnh. Checkpoint này hoàn tất khi apply thành công và metadata trả đúng tên role. Bước tiếp theo kiểm tra Certbot cùng quyền DNS challenge trước khi xin certificate.

### 4.16. Chạy thử DNS challenge trên AWS bằng Certbot

EC2 đã trả tên role mcf-aws-certbot qua IMDSv2. AWS API cũng xác nhận instance profile ở trạng thái associated và policy đã giới hạn quyền ghi vào TXT record trong hosted zone của project.

Certificate trên AWS dự kiến bao gồm hai hostname aws.mcf.todicode.tech và app.mcf.todicode.tech. Origin hostname phục vụ kiểm tra trực tiếp AWS, còn app hostname phục vụ địa chỉ chung sau khi cấu hình DNS failover. DNS-01 xác minh quyền quản lý hostname qua TXT record, nên có thể xác minh app hostname trong bước chuẩn bị certificate này.

Trong terminal Ubuntu trên EC2, kiểm tra Certbot và plugin.

```bash
certbot --version
sudo certbot plugins
```

Khi plugin dns-route53 đã được nhận diện với chức năng Authenticator, chạy thử quá trình xin certificate với Let's Encrypt staging.

```bash
sudo certbot certonly \
  --dns-route53 \
  --dry-run \
  --cert-name mcf-aws \
  -d aws.mcf.todicode.tech \
  -d app.mcf.todicode.tech
```

certonly thực hiện xin certificate. dns-route53 chọn plugin DNS-01 cập nhật Route 53. dry-run kiểm tra luồng xác minh với môi trường staging của Let's Encrypt. cert-name đặt tên quản lý certificate là mcf-aws. Mỗi tham số -d thêm một hostname vào yêu cầu certificate.

Certbot có thể hỏi email và điều khoản đăng ký ở lần chạy đầu. Người vận hành nhập email của mình và thực hiện các lựa chọn trong terminal. Plugin sử dụng temporary credentials của IAM role trên EC2 để tạo TXT challenge, đợi Route 53 đồng bộ, thực hiện xác minh và dọn TXT challenge.

Thông báo mong đợi khi hoàn tất.

```text
The dry run was successful.
```

Checkpoint này xác nhận Certbot cùng plugin hoạt động, quyền Route 53 đáp ứng DNS challenge và cả hai hostname được xác minh thành công trong staging. Bước tiếp theo xin certificate production rồi đưa certificate vào Kubernetes TLS Secret.

Kết quả thực hành đã trả Account registered và The dry run was successful cho cả aws.mcf.todicode.tech và app.mcf.todicode.tech. Checkpoint kiểm tra Certbot và DNS challenge đã hoàn tất.

### 4.17. Xin certificate production trên AWS

Trong terminal Ubuntu trên EC2, chạy yêu cầu certificate production với tên mcf-aws và hai hostname đã kiểm tra.

```bash
sudo certbot certonly \
  --dns-route53 \
  --cert-name mcf-aws \
  -d aws.mcf.todicode.tech \
  -d app.mcf.todicode.tech
```

Lệnh này sử dụng Let's Encrypt production. Certbot có thể yêu cầu đăng ký account production, email và xác nhận điều khoản trong terminal. Sau khi xác minh DNS thành công, kết quả mong đợi có thông báo Successfully received certificate.

Certbot lưu certificate cùng certificate chain tại /etc/letsencrypt/live/mcf-aws/fullchain.pem và private key tại /etc/letsencrypt/live/mcf-aws/privkey.pem. Hai file sẽ được dùng ở bước tạo Kubernetes TLS Secret.

Kiểm tra certificate đã cấp bằng lệnh sau trên EC2.

```bash
sudo certbot certificates
```

Đối chiếu Certificate Name là mcf-aws, Domains bao gồm aws.mcf.todicode.tech và app.mcf.todicode.tech, Expiry Date còn hiệu lực và các đường dẫn Certificate Path, Private Key Path thuộc /etc/letsencrypt/live/mcf-aws/. Checkpoint này hoàn tất khi certificate production được cấp và các thông tin được đối chiếu. Bước tiếp theo tạo TLS Secret trong namespace issues rồi cấu hình Ingress HTTPS.

Kết quả thực hành đã xác nhận certificate ECDSA cho hai hostname, còn hiệu lực tới 2027-02-11 17:22:35 UTC. Certificate Path và Private Key Path khớp các đường dẫn mcf-aws ở trên.

### 4.18. Tạo Kubernetes TLS Secret trên AWS

Trong terminal Ubuntu trên EC2, tạo hoặc cập nhật Secret issues-app-tls trong namespace issues từ certificate production vừa cấp.

```bash
sudo k3s kubectl -n issues create secret tls issues-app-tls \
  --cert=/etc/letsencrypt/live/mcf-aws/fullchain.pem \
  --key=/etc/letsencrypt/live/mcf-aws/privkey.pem \
  --dry-run=client -o yaml | sudo k3s kubectl apply -f -
```

create secret tls đọc certificate và private key để tạo cấu trúc Secret type kubernetes.io/tls. Tham số dry-run=client yêu cầu tạo cấu trúc resource ở phía client, còn -o yaml chuyển cấu trúc đó thành YAML. Dấu pipe truyền YAML sang kubectl apply -f - để áp dụng vào cluster. Có thể chạy lại cùng lệnh để cập nhật Secret từ certificate hiện tại.

Secret chứa hai trường tls.crt và tls.key, tương ứng với fullchain.pem và privkey.pem. Namespace issues khớp namespace của Ingress ứng dụng. Bước cấu hình HTTPS sẽ tham chiếu Secret bằng tên issues-app-tls.

Kiểm tra loại Secret và kích thước dữ liệu bằng lệnh sau.

```bash
sudo k3s kubectl -n issues describe secret issues-app-tls
```

Kết quả mong đợi có Name issues-app-tls, Namespace issues, Type kubernetes.io/tls và hai trường dữ liệu tls.crt, tls.key có kích thước lớn hơn 0 byte. Checkpoint này hoàn tất khi Secret được tạo và các thông tin trên được đối chiếu. Bước tiếp theo khai báo Ingress HTTPS cho AWS.

### 4.19. Khai báo Ingress HTTPS cho AWS

Tạo file deploy/kubernetes/app/app-ingress-https-aws.yaml trên laptop. Ingress HTTPS dùng entrypoint websecure của Traefik và TLS Secret issues-app-tls trong namespace issues.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: issues-app-https
  namespace: issues
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
spec:
  ingressClassName: traefik
  tls:
    - hosts:
        - aws.mcf.todicode.tech
        - app.mcf.todicode.tech
      secretName: issues-app-tls
  rules:
    - host: aws.mcf.todicode.tech
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: issues-app
                port:
                  number: 80
    - host: app.mcf.todicode.tech
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: issues-app
                port:
                  number: 80
```

metadata.name đặt tên resource issues-app-https. ingressClassName chọn Traefik xử lý Ingress. Annotation router.entrypoints chọn listener websecure, sử dụng cổng HTTPS 443 trong cấu hình K3s mặc định. router.tls true bật TLS cho router của Ingress.

tls.hosts khai báo hai hostname khớp certificate mcf-aws. secretName chọn Secret issues-app-tls đã được hướng dẫn tạo ở mục 4.18. Các rule host định tuyến request theo hostname, đường dẫn / kiểu Prefix chuyển các đường dẫn ứng dụng tới Service issues-app cổng 80. Traefik thực hiện TLS termination và gửi HTTP tới backend Service.

Luồng truy cập khi manifest được áp dụng.

```text
Browser → HTTPS 443 → Traefik → HTTP Service issues-app:80 → App Pod:8080
                         ↑
                TLS Secret issues-app-tls
```

Checkpoint này chuẩn bị manifest trong repository. Bước tiếp theo chuyển file lên EC2, apply và kiểm tra HTTPS bằng hostname AWS cùng certificate đã cấp.

### 4.20. Apply Ingress HTTPS AWS và kiểm tra từ laptop

Manifest app-ingress-https-aws.yaml đã được kiểm tra cú pháp YAML, tên resource, namespace, TLS Secret và hai hostname. Trước bước apply, endpoint HTTPS AWS đang trả certificate mặc định có subject và issuer CN=TRAEFIK DEFAULT CERT. Bước này cấu hình Traefik sử dụng certificate mcf-aws thông qua TLS Secret.

Trong Git Bash trên laptop, chuyển manifest lên EC2.

```bash
cd /d/multi-cloud-failover
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/app/app-ingress-https-aws.yaml \
  ubuntu@175.41.152.242:/home/ubuntu/app-ingress-https-aws.yaml
```

Trong terminal Ubuntu trên EC2, kiểm tra TLS Secret đã tạo ở mục 4.18. Đối chiếu Type kubernetes.io/tls và hai trường tls.crt, tls.key có dữ liệu.

```bash
sudo k3s kubectl -n issues describe secret issues-app-tls
```

Áp dụng manifest và kiểm tra Ingress.

```bash
sudo k3s kubectl apply -f /home/ubuntu/app-ingress-https-aws.yaml
sudo k3s kubectl -n issues describe ingress issues-app-https
```

Kết quả apply mong đợi là ingress.networking.k8s.io/issues-app-https created. Kết quả describe cần có Ingress Class traefik, TLS Secret issues-app-tls, hai rule host aws.mcf.todicode.tech và app.mcf.todicode.tech với backend issues-app:80.

Trong Git Bash trên laptop, kiểm tra HTTPS theo hostname AWS.

```bash
curl -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://aws.mcf.todicode.tech/version

curl -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://aws.mcf.todicode.tech/health/database
```

Cả hai endpoint cần trả HTTP 200. version cần có environment aws, region ap-southeast-1 và commit_sha c56fd3f30baee50fa779607dc0fb1a2133b53a9d. Writer health cần trả role primary và writable true. curl kiểm tra certificate chain và hostname theo cơ chế xác minh TLS mặc định của client.

Checkpoint này hoàn tất khi HTTPS qua hostname AWS được xác minh và ứng dụng trả đúng các thông tin trên. Bước tiếp theo triển khai certificate và HTTPS cho Azure, rồi hoàn thiện hostname chung cùng cơ chế gia hạn.

#### 4.20.1. Xử lý curl lỗi 43 trong Git Bash trên Windows

Ở lần kiểm tra ngày 2026-11-14, Git Bash chọn /mingw64/bin/curl, phiên bản 8.8.0. Đã tái hiện lỗi curl (43) A libcurl function was given a bad argument với endpoint HTTPS AWS trên executable này. Windows curl tại C:/Windows/System32/curl.exe, phiên bản 8.22.0, đã kiểm tra thành công cùng endpoint với xác minh TLS mặc định.

Trong Git Bash trên laptop, chỉ định executable Windows curl bằng đường dẫn đầy đủ.

```bash
/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://aws.mcf.todicode.tech/version

/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://aws.mcf.todicode.tech/health/database
```

Hai lệnh đã được chạy kiểm chứng ngay trong Git Bash và đều trả HTTP 200. version hiển thị environment aws, region ap-southeast-1, commit c56fd3f. Writer health hiển thị connected true, role primary và writable true. Kết quả này hoàn tất checkpoint HTTPS AWS và xác nhận TLS Secret đang phục vụ qua Ingress đã cấu hình.

## 5. Theo dõi tiến độ

- [x] Nghiệm thu đầu ra giai đoạn 5 và bắt đầu hướng dẫn DNS/HTTPS.
- [x] Xác định tên miền todicode.tech và tra cứu NS, hostname dự kiến, hosted zone trong tài khoản AWS.
- [x] Chọn nhánh mcf.todicode.tech và ba hostname app, aws, azure cho đồ án.
- [x] Đối chiếu profile default với IAM user và tài khoản sở hữu EC2 của project.
- [x] Chuẩn bị Terraform root module DNS và provider lock file theo mục 4.
- [x] Tạo providers.tf và chạy init/validate thành công cho root module DNS.
- [x] Khai báo aws_route53_zone.project và đối chiếu plan tạo một hosted zone.
- [x] Tạo public hosted zone mcf.todicode.tech bằng Terraform.
- [x] Lấy dns_zone_id và đủ bốn dns_name_servers từ Terraform output.
- [x] Delegate nhánh mcf từ DNS gốc tới Route 53 và kiểm tra DNS.
- [x] Chuẩn bị biến và terraform.tfvars chứa IP của hai origin.
- [x] Khai báo hai record A cho origin và đối chiếu plan tạo hai resource.
- [x] Apply hai record A origin và kiểm tra phân giải về đúng IP.
- [x] Kiểm tra HTTP qua hostname origin, đúng environment và writer health của mỗi cloud.
- [x] Cài Certbot và kiểm tra plugin dns-route53 trên AWS.
- [x] Khai báo IAM role Certbot với EC2 trust policy và đối chiếu plan.
- [x] Truyền dns_zone_id từ root module DNS vào root module AWS.
- [x] Khai báo policy Certbot giới hạn cập nhật TXT trong hosted zone của project.
- [x] Khai báo instance profile và đối chiếu plan gắn profile vào EC2.
- [x] Cấp quyền DNS challenge, gắn instance profile và kiểm tra role trên EC2.
- [x] Chạy thử Certbot DNS-01 thành công cho aws và app hostname trên AWS.
- [x] Xin certificate production mcf-aws và đối chiếu hostname, thời hạn, đường dẫn.
- [x] Tạo TLS Secret issues-app-tls trong namespace issues trên AWS.
- [x] Khai báo manifest Ingress HTTPS cho hostname aws và app trên AWS.
- [x] Apply Ingress HTTPS AWS và kiểm tra certificate, version, writer health qua HTTPS.
- [ ] Tạo record cho hai origin và đường truy cập ứng dụng chung.
- [ ] Cấu hình certificate, Ingress HTTPS và kiểm tra hai origin.
- [ ] Nghiệm thu hostname chung, writer health và cơ chế gia hạn certificate.

## 6. Tài liệu kỹ thuật

- [Route 53 public hosted zones](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/CreatingHostedZone.html).
- [Route 53 subdomain delegation](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/CreatingNewSubdomain.html).
- [Terraform dependency lock file](https://developer.hashicorp.com/terraform/language/files/dependency-lock).
- [Terraform init](https://developer.hashicorp.com/terraform/cli/commands/init).
- [Terraform validate](https://developer.hashicorp.com/terraform/cli/commands/validate).
- [Route 53 service endpoints](https://docs.aws.amazon.com/general/latest/gr/r53.html).
- [AWS CLI profiles](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html).
- [Terraform aws_route53_zone](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/route53_zone).
- [Terraform output values](https://developer.hashicorp.com/terraform/language/values/outputs).
- [Terraform apply](https://developer.hashicorp.com/terraform/cli/commands/apply).
- [Route 53 pricing](https://aws.amazon.com/route53/pricing/).
- [Terraform input variables](https://developer.hashicorp.com/terraform/language/values/variables).
- [Terraform aws_route53_record](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/route53_record).
- [Certbot DNS Route 53 plugin](https://certbot-dns-route53.readthedocs.io/en/stable/).
- [Let's Encrypt DNS-01](https://letsencrypt.org/docs/challenge-types/#dns-01-challenge).
- [Ubuntu 24.04 Route 53 plugin package](https://packages.ubuntu.com/noble/python3-certbot-dns-route53).
- [Kubernetes Ingress TLS](https://kubernetes.io/docs/concepts/services-networking/ingress/#tls).
- [EC2 SSH connection troubleshooting](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/TroubleshootingInstancesConnecting.html).
- [IAM roles for applications on EC2](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-ec2.html).
- [Terraform aws_iam_role](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role).
- [Terraform aws_iam_role_policy](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_role_policy).
- [Route 53 policy conditions](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/specifying-conditions-route53.html).
- [Terraform aws_iam_instance_profile](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_instance_profile).
- [Attach an IAM role to EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/attach-iam-role.html).
- [EC2 IMDSv2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html).
- [Certbot user guide](https://eff-certbot.readthedocs.io/en/stable/using.html).
- [Let's Encrypt staging](https://letsencrypt.org/docs/staging-environment/).
- [kubectl create secret tls](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_create/kubectl_create_secret_tls/).
- [Kubernetes TLS Secrets](https://kubernetes.io/docs/concepts/configuration/secret/#tls-secrets).
- [Traefik Kubernetes Ingress annotations](https://doc.traefik.io/traefik/reference/routing-configuration/kubernetes/ingress/).
- [K3s Traefik networking](https://docs.k3s.io/networking/networking-services#traefik-ingress-controller).
