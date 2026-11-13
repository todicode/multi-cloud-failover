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
