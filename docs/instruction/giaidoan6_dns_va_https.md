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

## 5. Theo dõi tiến độ

- [x] Nghiệm thu đầu ra giai đoạn 5 và bắt đầu hướng dẫn DNS/HTTPS.
- [x] Xác định tên miền todicode.tech và tra cứu NS, hostname dự kiến, hosted zone trong tài khoản AWS.
- [x] Chọn nhánh mcf.todicode.tech và ba hostname app, aws, azure cho đồ án.
- [ ] Chuẩn bị Terraform root module DNS và provider lock file theo mục 4.
- [ ] Tạo public hosted zone mcf.todicode.tech bằng Terraform.
- [ ] Delegate nhánh mcf từ DNS gốc tới Route 53 và kiểm tra DNS.
- [ ] Tạo record cho hai origin và đường truy cập ứng dụng chung.
- [ ] Cấu hình certificate, Ingress HTTPS và kiểm tra hai origin.
- [ ] Nghiệm thu hostname chung, writer health và cơ chế gia hạn certificate.

## 6. Tài liệu kỹ thuật

- [Route 53 public hosted zones](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/CreatingHostedZone.html).
- [Route 53 subdomain delegation](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/CreatingNewSubdomain.html).
- [Terraform dependency lock file](https://developer.hashicorp.com/terraform/language/files/dependency-lock).
