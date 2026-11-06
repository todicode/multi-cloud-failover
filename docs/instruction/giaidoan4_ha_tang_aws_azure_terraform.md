# Giai đoạn 4 — Hạ tầng AWS và Azure bằng Terraform

## 1. Mục tiêu và đầu ra

Chuẩn bị hai môi trường cloud độc lập cho mô hình AWS primary và Azure warm standby. Terraform mô tả tài nguyên hạ tầng; mỗi lớp được kiểm tra cấu hình, xem plan và xác nhận kết quả sau khi triển khai.

Điều kiện bắt đầu: đã hoàn thành [giai đoạn 3 — CI và container registry](giaidoan3_ci_va_container_registry.md), có tài khoản AWS và Azure riêng, cùng tên miền thuộc quyền quản lý.

| Thành phần | AWS | Azure |
|---|---|---|
| Mạng riêng | VPC và subnet | Virtual Network và subnet |
| Kết nối Internet | Internet Gateway, route table và Elastic IP | Public IP tĩnh và network interface |
| Kiểm soát truy cập | Security Group | Network Security Group |
| Máy chủ | EC2 Linux x86-64 | Linux VM x86-64 |
| Lưu trữ | EBS | Managed Disk |
| Truy cập quản trị | SSH bằng key | SSH bằng key |

Hai máy chủ sẽ chạy hai cụm K3s độc lập ở giai đoạn workload. Ứng dụng và PostgreSQL nằm trên từng máy chủ; PostgreSQL được tự quản lý, không sử dụng RDS trong thiết kế này. Sau khi hai môi trường sẵn sàng, WireGuard cung cấp đường truyền riêng cho WAL replication từ primary sang standby.

Phạm vi nghiệm thu giai đoạn 4 là hạ tầng: cấu hình Terraform, plan đã kiểm tra, hai máy chủ với địa chỉ truy cập, kết nối SSH và các quy tắc mạng phù hợp. Cấu hình K3s, WireGuard, PostgreSQL, ứng dụng, HTTPS và failover được hướng dẫn ở các giai đoạn tương ứng.

Trình tự học và triển khai:

Hoàn thiện kiến thức Azure cần cho kiến trúc, sau đó viết và kiểm tra Terraform phía AWS trước. Phần Azure được thực hiện tiếp theo để đối chiếu với hạ tầng AWS đã hiểu và triển khai. Mỗi bước cấu hình được thực hành riêng theo tiến độ.

```text
Công cụ → Xác thực tài khoản → Chọn region và cấu hình SSH
→ Kiến thức Azure nền tảng
→ Terraform AWS: cấu hình → plan → apply → xác nhận
→ Terraform Azure: cấu hình → plan → apply → xác nhận
```

Terraform được giữ trong cùng repository với ứng dụng ở `deploy/terraform/`, để cấu hình hạ tầng, workload và hướng dẫn được quản lý theo cùng project. AWS sử dụng root module `deploy/terraform/aws/`; Azure sẽ sử dụng root module riêng khi bắt đầu triển khai phía Azure. Mỗi root module có state riêng để thao tác từng cloud độc lập. Lab một người quản trị sử dụng local backend cho AWS theo mục 5.9. Quy mô hiện tại chưa cần một repository hạ tầng riêng.

Tài liệu được bổ sung theo từng bước thực hành. Lớp mạng AWS đã được triển khai và kiểm tra theo mục 5.10; compute, hạ tầng Azure và kết nối SSH tới máy chủ chưa được nghiệm thu.

## 2. Công cụ trên máy quản trị

Thực hiện từ Windows với Git Bash. Các CLI bản Windows có thể được gọi từ Git Bash khi thư mục cài đặt nằm trong `PATH`; không cần mở terminal WSL cho quy trình này.

| Công cụ | Vai trò |
|---|---|
| Terraform CLI | Đọc cấu hình hạ tầng, quản lý state, lập plan và thực hiện thay đổi |
| AWS CLI v2 | Xác thực và kiểm tra tài khoản AWS dùng cho project |
| Azure CLI | Đăng nhập và chọn subscription Azure dùng cho project |
| OpenSSH client | Kết nối quản trị hai máy chủ Linux |

Terraform gọi API cloud thông qua provider. Các CLI AWS/Azure phục vụ đăng nhập và kiểm tra danh tính; cơ chế xác thực provider được cấu hình ở bước tiếp theo.

### 2.1. Kiểm tra công cụ đã cài

Trong Git Bash:

```bash
cd /d/multi-cloud-failover
terraform version
aws --version
az version
ssh -V
```

Kết quả cần có: mỗi lệnh in thông tin phiên bản và không báo `command not found`. Terraform bản Windows có thể in `windows_amd64` dù được gọi từ Git Bash; đó là nền tảng của CLI trên máy quản trị, khác với image ứng dụng Linux AMD64 đã build ở giai đoạn 3.

Terraform `1.16.5` đã được xác nhận trên máy phát triển khi bắt đầu giai đoạn này. Thông báo có phiên bản mới không đồng nghĩa với lệnh thất bại. Ràng buộc phiên bản Terraform/provider và dependency lock file sẽ được thiết lập khi tạo cấu hình.

### 2.2. Cài Azure CLI nếu chưa có

Chạy lệnh sau trong terminal Windows, có thể dùng Git Bash:

```bash
winget install --exact --id Microsoft.AzureCLI
```

Hoàn tất trình cài đặt, đóng và mở lại Git Bash để terminal nhận `PATH` mới. Nếu dùng terminal tích hợp và vẫn chưa thấy lệnh, khởi động lại ứng dụng chứa terminal rồi kiểm tra:

```bash
az version
```

Lệnh cài đặt và yêu cầu mở lại terminal được mô tả trong [hướng dẫn Azure CLI cho Windows của Microsoft](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows). Nếu WinGet không khả dụng, trang này cũng cung cấp bộ cài MSI chính thức.

Bước này chỉ cài/kiểm tra công cụ trên máy quản trị. Các lệnh trên không đăng nhập tài khoản hoặc tạo tài nguyên cloud.

### 2.3. WinGet báo đã cài nhưng Git Bash chưa tìm thấy `az`

Nếu WinGet báo package đã tồn tại, kiểm tra môi trường terminal trước khi cài lại. Trên bản cài Windows 64-bit đã xác nhận, Azure CLI nằm ở `C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd`. Khi thư mục này đã có trong Windows system `PATH` nhưng chưa có trong môi trường của ứng dụng đang mở, terminal con cũng có thể tiếp tục dùng `PATH` cũ.

Để sử dụng ngay trong phiên Git Bash hiện tại:

```bash
export PATH="/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin:$PATH"
hash -r
az version
```

`export PATH=...` thêm thư mục CLI vào đường tìm lệnh của shell hiện tại và các tiến trình con, đồng thời giữ phần `PATH` cũ. Dấu ngoặc kép bảo vệ khoảng trắng trong đường dẫn. `hash -r` xóa cache vị trí lệnh của Bash. Trên máy đã kiểm tra, nhóm lệnh này trả Azure CLI `2.92.0`.

Lệnh export trên không sửa Windows `PATH` hoặc file khởi tạo shell. Để các phiên sau tự nhận Windows `PATH` đã cập nhật, đóng và mở lại ứng dụng chứa terminal, chẳng hạn VS Code hoặc Codex, rồi mở Git Bash mới. Nếu dùng Git Bash độc lập, đóng và mở lại Git Bash từ Start Menu.

Nếu thư mục cài đặt khác, dùng vị trí thực tế của `az.cmd` thay cho đường dẫn minh họa.

### 2.4. Git Bash vẫn thiếu lệnh sau khi mở lại

Mở lại terminal không bảo đảm mọi ứng dụng đã nhận Windows `PATH` mới: tiến trình khởi chạy terminal vẫn có thể giữ môi trường cũ. Cũng cần kiểm tra các file khởi tạo shell có ghi đè `PATH` hay không.

Trên máy phát triển đã kiểm tra, Windows system `PATH` có thư mục Azure CLI và các khai báo `PATH` trong profile người dùng giữ lại giá trị cũ. Git Bash khởi động với `PATH` đọc mới từ Windows registry tìm được `az`, trong khi bản khởi động với môi trường kế thừa của tiến trình công cụ không tìm được. Điều này xác nhận sự khác nhau giữa môi trường tiến trình và cấu hình Windows đã lưu; chưa xác định tiến trình cha của terminal mà người dùng đang sử dụng.

Để Git Bash luôn bổ sung đường dẫn CLI khi khởi động, có thể thêm cấu hình vào `~/.bashrc`. Lệnh dưới đây thực hiện một lần, dành cho đường dẫn Azure CLI 64-bit đã xác nhận:

```bash
printf '\nexport PATH="/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin:$PATH"\n' >> ~/.bashrc
source ~/.bashrc
hash -r
az version
```

Dấu `>>` nối dòng vào cuối file hiện có. Dấu nháy đơn ở lệnh `printf` giữ nguyên chữ `$PATH` trong nội dung ghi; Bash sẽ mở rộng biến này khi nạp `.bashrc`. `source` nạp lại cấu hình ngay trong shell hiện tại.

Đường dẫn trên là cấu hình của máy quản trị, không nằm trong repository. Không chạy lệnh nối thêm nhiều lần; nếu dòng export đã tồn tại, chỉ cần `source ~/.bashrc`, `hash -r` và kiểm tra lại. Login shell cần nạp `.bashrc` qua profile; trên máy đã kiểm tra, `.bash_profile` có dòng nạp `.bashrc`.

## 3. Kiến thức Azure nền tảng

### 3.1. Subscription, Resource Group và resource

**Subscription** là phạm vi quản lý tài nguyên, chi phí và quota. Có thể liên hệ với AWS Account ở các khía cạnh này; tài khoản đăng nhập và subscription là hai khái niệm riêng. Một người có thể được cấp quyền trên nhiều subscription. Xem [đối chiếu tài khoản AWS và Azure của Microsoft](https://learn.microsoft.com/en-us/azure/architecture/aws-professional/accounts).

**Resource** là tài nguyên cụ thể, ví dụ VM, đĩa, Virtual Network hoặc Public IP. **Resource Group (RG)** gom các tài nguyên liên quan để quản lý cùng vòng đời. Xem [khái niệm Resource Group](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/overview#what-is-a-resource-group).

Ví dụ cấu trúc dự kiến cho phía Azure của project:

```text
Subscription được chọn
└── Resource Group: mcf-azure-rg
    ├── Linux VM          → máy chủ standby
    ├── Managed Disk      → đĩa máy chủ
    ├── Virtual Network   → mạng riêng
    ├── Network Interface → card mạng máy chủ
    ├── Public IP         → địa chỉ truy cập công khai
    └── NSG               → quy tắc lọc lưu lượng
```

Đây là sơ đồ dự kiến, chưa phải inventory đã tạo. RG là nhóm quản lý; VNet mới là thành phần mạng tương ứng với AWS VPC. Đặt cùng RG không tự tạo kết nối mạng giữa các tài nguyên. Xóa RG cũng xóa các tài nguyên trong nhóm, nên nhóm thường được chọn theo vòng đời. Hướng dẫn tổ chức tài nguyên: [Microsoft Cloud Adoption Framework](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-setup-guide/organize-resources).

Trong đồ án, chọn đúng subscription để triển khai và thanh toán trong phạm vi cá nhân; RG gom phần hạ tầng Azure của project. Tenant, quyền truy cập và các thành phần mạng được giải thích ở những phần tiếp theo.

### 3.2. Tenant và quyền truy cập tài nguyên

**Tenant** là một môi trường Microsoft Entra ID quản lý danh tính, như user và group. Tenant hiển thị tên trường khi đăng nhập cho biết thư mục tổ chức gắn với subscription được chọn; quyền thực tế của người dùng cần kiểm tra riêng. Xem [Microsoft Entra ID](https://learn.microsoft.com/en-us/entra/fundamentals/whatis).

Liên hệ AWS IAM: Azure dùng Microsoft Entra ID cho danh tính và Azure RBAC để cấp quyền trên tài nguyên. **Đăng nhập** xác nhận người dùng là ai; **phân quyền** xác định người đó được thực hiện thao tác nào. Tenant và AWS Account không phải hai khái niệm tương đương hoàn toàn.

Một Azure RBAC role assignment gồm:

```text
Ai được cấp quyền + Role nào + Scope áp dụng
```

Ví dụ: user được gán Contributor trên RG `mcf-azure-rg` có quyền quản lý hạ tầng trong RG đó theo role; assignment này không tự cấp quyền quản lý các RG khác. Scope ở subscription áp dụng xuống các RG và tài nguyên bên dưới. Xem [Azure RBAC](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview).

| Role | Quyền quản lý ở scope được gán |
|---|---|
| Reader | Xem tài nguyên |
| Contributor | Tạo, sửa, xóa tài nguyên; không được cấp Azure RBAC role cho người khác |
| Owner | Quản lý tài nguyên và cấp Azure RBAC role |

Đây là quyền quản lý tài nguyên, không mặc nhiên là quyền đọc mọi dữ liệu bên trong dịch vụ. Owner của một subscription không tự trở thành quản trị viên tenant của trường. Xem [phân biệt Azure roles và Entra roles](https://learn.microsoft.com/en-us/azure/role-based-access-control/rbac-and-directory-admin-roles) và [định nghĩa role](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/privileged).

Để kiểm tra quyền cá nhân, mở Azure Portal → Subscriptions → subscription của đồ án → Access control (IAM) → View my access. Ghi nhận role và scope hiển thị, gồm quyền kế thừa nếu có; không thay đổi role assignment ở bước kiểm tra này. Xem [hướng dẫn kiểm tra quyền](https://learn.microsoft.com/en-us/azure/role-based-access-control/check-access).

Trạng thái subscription `Enabled` và việc đăng nhập thành công chưa chứng minh đã có quyền tạo VM. Khả năng triển khai còn phụ thuộc role, policy và quota của subscription.

Kết quả kiểm tra qua `View my access` tại subscription của đồ án: người dùng xác nhận có role `Owner`. Quyền quản lý tài nguyên và role assignment có hiệu lực trong phạm vi subscription này; policy, quota và khả năng cấp VM tại region được kiểm tra riêng trước khi triển khai.

### 3.3. VNet và Subnet: đối chiếu AWS VPC

Azure **Virtual Network (VNet)** cung cấp mạng riêng cho tài nguyên, tương ứng về mục đích với AWS VPC. **Subnet** chia không gian địa chỉ của VNet thành các dải nhỏ hơn. Dải subnet phải nằm trong không gian địa chỉ VNet và không chồng lấn các subnet khác trong VNet.

Ví dụ địa chỉ dự kiến cho phía Azure:

```text
VNet: 10.30.0.0/16
└── Subnet: 10.30.1.0/24
    └── VM standby qua card mạng
        └── Private IP minh họa: 10.30.1.10
```

`/16` là dải lớn bao gồm subnet `/24` trên. Private IP này là địa chỉ nội bộ, không phải địa chỉ truy cập trực tiếp từ laptop qua Internet. Public IP, card mạng và quy tắc truy cập được giải thích ở phần sau. Xem [Azure Virtual Network](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-overview).

Khác biệt về Availability Zone: AWS subnet thuộc một AZ; Azure subnet có phạm vi trong một region và có thể chứa tài nguyên ở nhiều AZ của region đó. Một subnet Azure không tự tạo nhiều bản sao VM. Xem [AWS subnet basics](https://docs.aws.amazon.com/vpc/latest/userguide/configure-subnets.html#subnet-basics) và [đối chiếu mạng AWS/Azure](https://learn.microsoft.com/en-us/azure/architecture/aws-professional/networking#azure-virtual-networks-and-aws-vpcs).

Trong thiết kế project, AWS VPC dùng `10.29.0.0/16`, Azure VNet dùng `10.30.0.0/16`. Hai mạng không tự kết nối; đường truyền replication sẽ được thiết lập bằng WireGuard giữa hai máy chủ. Dải địa chỉ này là thiết kế dự kiến, chưa phải inventory đã tạo.

Resource Group gom tài nguyên để quản lý; VNet/Subnet tổ chức kết nối mạng. Bước kiến thức này chưa tạo tài nguyên hoặc thay đổi cấu hình cloud.

### 3.4. NIC, Private IP và Public IP

Azure **Network Interface (NIC)** là card mạng ảo gắn vào VM, có thể liên hệ với AWS ENI. Cấu hình IP của NIC chọn subnet, private IP và có thể tham chiếu tài nguyên Public IP. Xem [Azure network interface](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-network-network-interface).

Private IP được cấp từ dải subnet; ví dụ `10.30.1.10` trong `10.30.1.0/24`. Đây là địa chỉ nội bộ. Truy cập từ laptop qua Internet cần đường kết nối phù hợp, chẳng hạn Public IP hoặc VPN. Private IP có thể cấp dynamic hoặc static; địa chỉ ví dụ chưa phải giá trị thực tế đã được cấp. Xem [Private IP](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/private-ip-addresses).

Project dự kiến dùng **Standard Public IPv4 với cấp phát Static**, liên hệ với vai trò IP công khai ổn định của AWS Elastic IP. Public IP là tài nguyên riêng, được liên kết với IP configuration của NIC:

```text
Internet → Public IP → NIC có Private IP → VM standby
```

Giữ nguyên tài nguyên Static Public IP giúp duy trì địa chỉ cho SSH, origin DNS và WireGuard. Có Public IP vẫn cần quy tắc NSG cho phép kết nối đến dịch vụ. Xem [Public IP trong Azure](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/public-ip-addresses).

Trong đồ án, VNet/Subnet tổ chức mạng; NIC nối VM vào subnet; Public IP cung cấp địa chỉ công khai cho máy chủ. Chưa tạo tài nguyên ở bước kiến thức này.

### 3.5. Network Security Group (NSG)

NSG lọc lưu lượng inbound/outbound theo nguồn, đích, giao thức và cổng. Giống AWS Security Group, NSG là stateful: lưu lượng phản hồi của kết nối được cho phép không cần rule mở chiều ngược tương ứng. Khác AWS SG chỉ có Allow, NSG có cả Allow/Deny và priority; số nhỏ được xét trước, khớp rule thì dừng xét trong NSG. Xem [Azure NSG](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview) và [AWS SG rules](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html).

NSG có thể gắn ở subnet hoặc NIC. Project dự kiến gắn ở NIC của VM standby. Nếu dùng NSG ở cả hai vị trí, lưu lượng phải được cả hai cho phép. Xem [cách NSG lọc lưu lượng](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-group-how-it-works).

Các rule inbound dự kiến cho Azure:

| Cổng | Giao thức | Nguồn cho phép | Mục đích |
|---|---|---|---|
| 22 | TCP | Public IPv4 của máy quản trị, `/32` | SSH |
| 80 | TCP | Internet | HTTP/redirect khi cấu hình dịch vụ |
| 443 | TCP | Internet | HTTPS origin và health check |
| 51820 | UDP | Public IPv4 của máy AWS, `/32` | WireGuard giữa hai máy chủ |

Không thêm rule mở TCP 5432 trực tiếp ra Internet; PostgreSQL replication đi trong tunnel WireGuard. Rule 51820 được cấu hình khi thiết lập tunnel ở bước workload.

NSG có sẵn rule cho phép VirtualNetwork/AzureLoadBalancer và DenyAllInbound; không hiểu mặc định này là cấm mọi nguồn. Project dùng các rule tùy chỉnh cho các kết nối Internet cần thiết. NSG chỉ lọc gói tin; dịch vụ trên VM phải thực sự chạy và lắng nghe đúng cổng mới kết nối được.

### 3.6. VM, Managed Disk và trạng thái dừng máy

Azure VM tương ứng với EC2 về vai trò máy chủ ảo. VM size xác định cấu hình compute, tương tự instance type; OS image chọn hệ điều hành, có thể liên hệ với AMI. Project dự kiến dùng Ubuntu 24.04 x86-64 để chạy K3s, ứng dụng và PostgreSQL standby. VM size sẽ được chọn sau khi kiểm tra region, quota và chi phí. Xem [Azure VM](https://learn.microsoft.com/en-us/azure/virtual-machines/overview).

**Managed Disk** là block storage cho VM, liên hệ với AWS EBS. OS disk chứa hệ điều hành; có thể gắn thêm data disk để lưu dữ liệu riêng. Trong thiết kế lab hiện tại, dữ liệu PostgreSQL qua K3s local-path được đặt trên filesystem của máy chủ, trên managed OS disk:

```text
PostgreSQL → PVC/local-path → filesystem VM → Managed Disk
```

Azure quản lý hạ tầng đĩa, còn PostgreSQL vẫn do project tự cài và vận hành. Không đặt dữ liệu bền vững vào temporary disk. Xem [Managed Disk](https://learn.microsoft.com/en-us/azure/virtual-machines/managed-disks-overview).

Đĩa dự kiến thuộc loại Standard SSD; dung lượng cần đáp ứng tối thiểu của OS image và workload. Đây là lựa chọn thiết kế cho lab, chưa nghiệm thu bằng benchmark. Xem [các loại đĩa](https://learn.microsoft.com/en-us/azure/virtual-machines/disks-types).

Với compute on-demand, phân biệt hai trạng thái:

| Trạng thái | Tính phí compute |
|---|---|
| Stopped / Stopped (Allocated) | Vẫn tính phí |
| Stopped (Deallocated) | Không tính phí compute |

Shutdown từ trong Ubuntu có thể để VM ở Stopped (Allocated). Managed Disk và tài nguyên mạng được giữ lại có thể tiếp tục tính phí khi compute đã deallocated. Vì thế kiểm tra power state và các tài nguyên còn tồn tại khi kết thúc buổi lab. Xem [trạng thái và billing](https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing).

Azure warm standby trong bài thử failover phải đang hoạt động và nhận WAL. Deallocate dùng khi tạm ngừng thực hành; máy đang tắt không thể đảm nhiệm warm standby trong thời gian đó.

### 3.7. Region, quota và khả năng cấp VM

Azure region tương ứng về vai trò với AWS region: vị trí triển khai tài nguyên. Ví dụ, Azure `southeastasia` là Southeast Asia tại Singapore. VM size là cấu hình máy, tương tự instance type. Một size có thể không khả dụng cho subscription hoặc tại region/zone cụ thể. Xem [danh sách region](https://learn.microsoft.com/en-us/azure/reliability/regions-list) và [SKU availability](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-sku-not-available).

Quota là hạn mức tài nguyên, liên hệ với AWS Service Quotas. Credit là ngân sách, không phải quota compute. Azure kiểm tra cả tổng vCPU theo region và vCPU theo family; ví dụ VM 2 vCPU cần đủ phần còn lại của cả hai hạn mức. Có đủ quota vẫn cần capacity thực tế. Xem [vCPU quotas](https://learn.microsoft.com/en-us/azure/virtual-machines/quotas).

Trước khi chốt size cần kiểm tra: region/policy cho phép, restriction của SKU, quota còn lại, capacity khi cấp máy, kiến trúc x86-64 và chi phí dự kiến. Chưa kết luận một size tạo được hoặc phù hợp ngân sách chỉ từ tên SKU.

### 3.8. Azure Policy: quy định áp dụng cho tài nguyên

Azure RBAC cấp quyền thực hiện thao tác; Azure Policy kiểm tra tài nguyên có tuân thủ quy định được gán hay không. Ví dụ policy có thể giới hạn region, VM SKU hoặc yêu cầu tag. Role Owner vẫn chịu policy áp dụng. Xem [Azure Policy](https://learn.microsoft.com/en-us/azure/governance/policy/overview).

Có thể liên hệ vai trò giới hạn của quy định tổ chức với AWS SCP, nhưng cơ chế không tương đương hoàn toàn: SCP giới hạn quyền thao tác, còn Azure Policy có thể đánh giá thuộc tính tài nguyên và áp dụng các effect như Audit, Deny hoặc Modify. Xem [AWS SCP](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html).

Policy assignment là việc áp dụng một policy hoặc bộ policy tại một scope. Kiểm tra cả assignment tại subscription và assignment được kế thừa; đọc parameters, phạm vi loại trừ và enforcement trước khi kết luận ảnh hưởng. Không suy ra tenant mang tên trường đồng nghĩa với một policy cụ thể đã được gán.

### 3.9. Routing và Internet connectivity

Routing quyết định gói tin đi theo đường nào; NSG quyết định lưu lượng có được phép qua hay không. Với EC2 public IPv4, AWS sử dụng route đến Internet Gateway. Azure tự cung cấp system routes cho subnet, gồm `0.0.0.0/0` với next hop `Internet`; custom route có thể thay đổi đường đi. Xem [AWS Internet Gateway](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Internet_Gateway.html) và [Azure system routes](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview).

Project dùng Public IPv4 gắn với NIC của VM làm explicit outbound connectivity, kết hợp system routes và NSG cho phép lưu lượng cần thiết. Không cần tạo một tài nguyên Internet Gateway tương tự AWS cho VNet của thiết kế này. Khi outbound trực tiếp qua instance-level Public IP, Azure ánh xạ IP nội bộ/công khai theo quan hệ 1:1. Xem [outbound qua Public IP của VM](https://learn.microsoft.com/en-us/azure/load-balancer/load-balancer-outbound-connections#2-assign-a-public-ip-to-the-virtual-machine).

```text
Inbound:  Laptop/browser → Public IP → NSG cho phép → VM/dịch vụ
Outbound: VM → NIC → Azure ánh xạ sang Public IP → Internet
```

Outbound phục vụ cài package Ubuntu, tải K3s và pull image GHCR. Inbound phục vụ SSH, HTTPS và WireGuard theo các rule đã thiết kế. Cả hai chiều còn phụ thuộc cấu hình host, dịch vụ và DNS phù hợp.

VNet mới sử dụng API phát hành sau 2026-03-31 mặc định dùng private subnet, cần explicit outbound khi truy cập public endpoints. Public IP gắn NIC là một phương án explicit được hỗ trợ. Default Internet route và NSG Allow outbound riêng lẻ chưa bảo đảm có đường truy cập Internet hoàn chỉnh. Xem [default outbound access](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/default-outbound-access).

Đây là thiết kế kết nối dự kiến; kiểm tra HTTP outbound, DNS và inbound SSH khi VM được tạo ở bước triển khai.

### 3.10. SSH key và khởi tạo Ubuntu

SSH key pair của Azure Linux VM dùng cùng nguyên lý với EC2: public key đặt trên máy chủ, private key giữ trên máy quản trị để chứng minh danh tính khi kết nối. Azure hỗ trợ RSA và ED25519; lab chuẩn bị key ED25519 riêng tên `mcf-lab`. Xem [SSH keys trong Azure](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/create-ssh-keys-detailed).

```text
Máy quản trị: private key → SSH xác thực → VM: public key trong authorized_keys
```

Role Owner/phiên `az login` quản lý tài nguyên qua API; SSH key phục vụ đăng nhập hệ điều hành Ubuntu. Đây là hai cơ chế truy cập khác nhau. Truy cập SSH cần đúng username/key, dịch vụ sshd hoạt động, địa chỉ truy cập và NSG cho phép TCP 22 từ IP quản trị.

Đối chiếu khởi tạo phần mềm: cơ chế EC2 User Data có thể liên hệ với Azure Custom Data được cloud-init xử lý trên Ubuntu khi provisioning/first boot. Custom Data mang nội dung cấu hình; cloud-init là thành phần trong máy thực thi việc khởi tạo. Script bootstrap và việc xác nhận hoàn tất được hướng dẫn sau bước chuẩn bị key. Xem [cloud-init](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/using-cloud-init) và [Custom Data](https://learn.microsoft.com/en-us/azure/virtual-machines/custom-data).

### 3.11. Custom Data và cloud-init thực thi bootstrap

AWS EC2 User Data và Azure Custom Data đều có thể mang nội dung khởi tạo cho máy Linux. Trên Ubuntu image hỗ trợ cloud-init, Azure đưa Custom Data vào VM, rồi cloud-init xử lý cấu hình/script trong quá trình first boot. Xem [EC2 User Data](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html) và [Azure cloud-init](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/using-cloud-init).

```text
Cấu hình/script trong project
→ Terraform gửi nội dung qua Azure API dưới dạng Custom Data
→ Ubuntu khởi động
→ cloud-init trong VM thực thi bootstrap
```

Custom Data là nội dung đầu vào; cloud-init là thành phần xử lý trong hệ điều hành. Terraform mô tả và gửi cấu hình; script được thực thi trong VM. Ví dụ minh họa script để ghi một dấu hiệu đã thực thi:

```bash
#!/bin/bash
echo "Bootstrap script executed" > /etc/mcf-bootstrap-ready
```

Đây là nội dung minh họa cho VM, chưa phải lệnh chạy ở Git Bash hoặc bootstrap hoàn chỉnh của project. File marker chỉ chứng minh dòng script này đã chạy; readiness của web/database cần kiểm tra riêng. Script khởi tạo kiểu này mặc định theo vòng đời instance, không tự chạy lại toàn bộ mỗi lần reboot.

Azure Custom Data truyền qua API dùng Base64; Base64 là mã hóa biểu diễn, không phải mã hóa bảo mật. Khi viết cấu hình Terraform sẽ xử lý phần biểu diễn theo yêu cầu provider. Xem [Custom Data](https://learn.microsoft.com/en-us/azure/virtual-machines/custom-data).

Trạng thái VM đã provision thành công có thể xuất hiện khi cloud-init vẫn đang xử lý Custom Data. Sau khi có VM và SSH vào Ubuntu, kiểm tra:

```bash
sudo cloud-init status --wait
sudo tail -n 50 /var/log/cloud-init-output.log
```

Đọc trạng thái, exit code và log để xác định thành công hoặc lỗi; việc lệnh chờ kết thúc không tự chứng minh ứng dụng đã healthy. Chạy lệnh chờ từ phiên SSH, không đặt nó bên trong script cloud-init đang thực thi. Xem [chờ cloud-init hoàn tất](https://docs.cloud-init.io/en/latest/howto/wait_for_cloud_init.html).

### 3.12. Terraform provider, resource và dependency

Terraform đọc cấu hình mô tả trạng thái hạ tầng mong muốn. Provider là plugin làm việc với API dịch vụ: `hashicorp/aws` cho AWS, `hashicorp/azurerm` cho Azure Resource Manager. Trong quy trình này, Azure CLI login cung cấp một phương thức xác thực; provider dùng API để quản lý tài nguyên. Xem [providers](https://developer.hashicorp.com/terraform/language/providers).

Resource block khai báo một tài nguyên Terraform sẽ quản lý. Ví dụ minh họa, chưa phải cấu hình hoàn chỉnh để chạy độc lập:

```hcl
resource "azurerm_resource_group" "standby" {
  name     = "mcf-azure-rg"
  location = "southeastasia"
}
```

- `azurerm_resource_group`: loại resource của provider AzureRM.
- `standby`: tên nội bộ dùng tham chiếu trong Terraform.
- `name`: tên Resource Group trong Azure.
- `location`: location của Resource Group; từng tài nguyên bên trong có cấu hình location riêng khi loại tài nguyên đó yêu cầu.

Địa chỉ Terraform của resource là `azurerm_resource_group.standby`. Trong cấu hình VNet sau này, tham chiếu tên RG bằng:

```hcl
resource_group_name = azurerm_resource_group.standby.name
```

Biểu thức này đọc thuộc tính `name`, đồng thời giúp Terraform nhận biết dependency của VNet vào RG. Khác với ghi cố định chuỗi tên RG ở mọi chỗ, tham chiếu biểu đạt quan hệ giữa các tài nguyên. Terraform lập graph dependency để xác định thứ tự thao tác, thay vì chạy file theo thứ tự từ trên xuống. Xem [resource blocks](https://developer.hashicorp.com/terraform/language/resources) và [references](https://developer.hashicorp.com/terraform/language/expressions/references).

Một nhánh dependency chính của thiết kế Azure:

```text
Resource Group → VNet → Subnet → NIC → VM
```

Public IP, NSG và association tạo các nhánh liên quan khi khai báo chúng. File cấu hình có thể được chia theo mục đích; Terraform đọc các file `.tf` trong cùng root module như một cấu hình thống nhất. Các ví dụ ở phần kiến thức này chỉ được ghi trong hướng dẫn; provider requirements, variables, xác thực và các lệnh init/plan được bổ sung ở bước thực hành tiếp theo.

### 3.13. Vận hành và phân loại lỗi theo lớp

Khi triển khai, xác định lớp đang lỗi trước khi chọn log:

| Lớp | Ví dụ triệu chứng | Nơi kiểm tra |
|---|---|---|
| Azure quản lý tài nguyên | API từ chối tạo VM do policy, quota, size/zone hoặc quyền | Thông báo Terraform/API, Activity log của subscription hoặc resource |
| Ubuntu khởi tạo | Máy đã có nhưng package/script bootstrap lỗi | SSH, cloud-init status, cloud-init log/output log |
| Dịch vụ trong VM | K3s, pod hoặc ứng dụng/database lỗi | Trạng thái và log dịch vụ/pod, kết nối và endpoint của ứng dụng |

Azure Activity log ghi các thao tác quản lý như tạo/sửa/xóa tài nguyên; có thể liên hệ với management events của AWS CloudTrail. Log trong Ubuntu hoặc log request của web cần kiểm tra ở lớp tương ứng. Xem [Activity log](https://learn.microsoft.com/en-us/azure/azure-monitor/fundamentals/activity-log) và [CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html).

Khi xem một event lỗi, đọc operation, status, thời điểm và error code/message; đối chiếu với thao tác vừa thực hiện. Không phải lỗi cấu hình local của Terraform nào cũng tạo event trên Azure vì có thể chưa gửi API request.

Phân biệt ba loại trạng thái:

- `ProvisioningState=Succeeded`: thao tác provisioning đã hoàn thành theo Azure.
- `PowerState=Running`: máy đang chạy.
- Dịch vụ healthy: do kiểm tra thực tế của K3s, ứng dụng và database xác định.

Cloud-init có thể tiếp tục thực thi script sau khi VM được báo đã provision. Khi chưa SSH được, kiểm tra thêm power state, Public IP, NSG và mạng; chưa thể kết luận chỉ từ triệu chứng timeout rằng script hoặc ứng dụng bị lỗi. Xem [VM states](https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing) và [cloud-init troubleshooting](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/cloud-init-troubleshooting).

Áp dụng vào các endpoint hiện có của project:

| Kiểm tra | Vai trò |
|---|---|
| `/health/live` | Liveness của tiến trình web |
| `/api/database/status` | Kết nối, role và khả năng ghi của database |
| `/health/database` | Writer health: HTTP 200 khi database writable, HTTP 503 nếu không writable hoặc lỗi kết nối |

Azure standby kết nối được nhưng read-only là trạng thái bình thường trước promotion. Khi đó writer health trả 503 theo thiết kế; kết hợp role/status với liveness để đọc đúng kết quả. Chi tiết chẩn đoán K3s, WireGuard và PostgreSQL được thực hành ở giai đoạn workload.

Phần nền Azure phục vụ hạ tầng đã bao quát danh tính, tổ chức tài nguyên, mạng, VM/đĩa, giới hạn, chi phí, bootstrap và cách xác định lớp lỗi. Bước viết Terraform triển khai tiếp theo bắt đầu ở phía AWS theo trình tự của giai đoạn này.

## 4. Đăng nhập Azure CLI và xác nhận subscription

Subscription Azure for Students được chọn cho phía Azure standby. Credit dùng cho các dịch vụ đủ điều kiện của subscription; chọn kích thước VM, region và thời gian chạy sau khi kiểm tra quota và chi phí. Theo dõi mức sử dụng ở [Education Hub và Cost Management](https://learn.microsoft.com/en-us/azure/education-hub/navigate-costs).

### 4.1. Đăng nhập bằng tài khoản sở hữu subscription

Trong Git Bash:

```bash
az login
```

Hoàn tất đăng nhập trong cửa sổ tài khoản Windows hoặc giao diện đăng nhập được mở. Dùng tài khoản có quyền trên subscription Azure for Students. Nếu CLI hiển thị danh sách để chọn subscription, chọn dòng ứng với subscription dùng cho đồ án.

Kiểm tra danh sách subscription và lựa chọn mặc định:

```bash
az account list --query "[].{Name:name,State:state,Default:isDefault}" --output table
```

Ý nghĩa các cột:

- `Name`: tên subscription.
- `State`: trạng thái; subscription dùng để triển khai cần ở trạng thái `Enabled`.
- `Default`: `True` cho subscription mặc định của CLI. Các lệnh không chỉ định subscription thường sử dụng lựa chọn này.

Nếu subscription của đồ án chưa là mặc định, dừng ở bước xác nhận danh sách để chọn lại ở bước kế tiếp. Các lệnh trên đăng nhập và đọc thông tin subscription, không tạo VM hoặc tài nguyên cloud.

Tài liệu chính thức: [đăng nhập tương tác](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-interactively) và [quản lý subscription bằng Azure CLI](https://learn.microsoft.com/en-us/cli/azure/manage-azure-subscriptions-azure-cli).

Kết quả thực hành đã xác nhận: Azure CLI đăng nhập thành công; subscription `Azure for Students` có `State=Enabled` và `Default=True`. Bước này xác nhận ngữ cảnh subscription của CLI; quyền tạo từng loại tài nguyên và quota sẽ được kiểm tra ở các bước tiếp theo.

### 4.2. Đọc quota tại region khảo sát

Trong Git Bash, dùng subscription mặc định đã xác nhận, khảo sát Southeast Asia:

```bash
az vm list-usage --location southeastasia --output table
```

`southeastasia` là region khảo sát ban đầu, chưa phải quyết định triển khai. Lệnh chỉ đọc hạn mức và mức sử dụng; không tạo VM. Nếu bị từ chối hoặc không trả dữ liệu, ghi nhận thông báo để kiểm tra quyền/region thay vì thử tạo máy.

Đọc các cột `Name`, `CurrentValue` và `Limit`. Chú ý `Total Regional vCPUs` và hạn mức family của size dự định dùng. Ví dụ minh họa: limit 4, đang dùng 2 thì còn 2 vCPU theo hạn mức đó. Kết quả list-usage chưa xác nhận policy cho phép region, restriction của SKU, capacity hoặc chi phí. Các kiểm tra này được bổ sung sau khi có kết quả quota thực tế.

Kết quả quota đã nhận từ lần kiểm tra thực tế:

| Hạn mức tại `southeastasia` | CurrentValue | Limit |
|---|---|---|
| Total Regional vCPUs | 0 | 6 |
| Standard BS Family vCPUs | 0 | 4 |
| Standard Basv2 Family vCPUs | 0 | 10 |
| Standard Bsv2 Family vCPUs | 0 | 10 |

Quota hiện đủ cho một VM 2 vCPU thuộc Bsv2 hoặc Basv2. Tổng vCPU các family vẫn chịu giới hạn region là 6; limit 10 của một family không nâng tổng region lên 10. Kết quả là ảnh chụp hạn mức tại thời điểm kiểm tra và cần đối chiếu lại nếu tài nguyên hoặc quota thay đổi.

### 4.3. Kiểm tra restriction của VM size cụ thể

Hai ứng viên x86-64 để khảo sát cho lab:

- `Standard_B2ls_v2`: 2 vCPU, 4 GiB RAM, family Bsv2.
- `Standard_B2als_v2`: 2 vCPU, 4 GiB RAM, family Basv2.

Đối chiếu thông số: [Bsv2](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/bsv2-series) và [Basv2](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/basv2-series). Đây là ứng viên khảo sát, chưa chốt size hoặc chi phí. Khả năng đáp ứng workload cần được kiểm tra khi triển khai.

Trong Git Bash:

```bash
az vm list-skus \
  --location southeastasia \
  --resource-type virtualMachines \
  --size Standard_B2 \
  --all \
  --query "[?name=='Standard_B2ls_v2' || name=='Standard_B2als_v2'].{Name:name,Family:family,Restrictions:restrictions}" \
  --output json
```

`--size` tìm theo một phần tên; biểu thức `--query` giữ lại đúng hai tên cần kiểm tra. `--all` bao gồm SKU có restriction để không nhầm việc không thấy máy với việc không có giới hạn. Lệnh chỉ đọc danh mục SKU.

Trong từng object, `Restrictions: []` nghĩa là API không báo restriction của SKU đó. Nếu có restriction, đọc `type`, `reasonCode` và phạm vi location/zone. Nếu cả kết quả chỉ là `[]`, truy vấn không tìm thấy hai size tại region đó; không coi đây là bằng chứng size khả dụng.

Không có restriction trong danh mục vẫn chưa xác nhận mọi Azure Policy cho phép triển khai hoặc capacity tại thời điểm tạo máy. Cần kiểm tra policy và giá trước khi chốt cấu hình. Xem [hướng dẫn SKU availability](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-sku-not-available).

Kết quả thực tế cho cả hai ứng viên: có restriction `reasonCode=NotAvailableForSubscription`, `type=Zone`, `restrictionInfo.locations=[southeastasia]`, `restrictionInfo.zones=[2]`. Metadata này giới hạn triển khai vào logical Zone 2 của subscription tại region đã chọn; không có restriction `type=Location` trong kết quả đã nhận. Chưa kết luận cả region bị cấm hoặc một zone khác chắc chắn cấp được máy.

### 4.4. Đối chiếu zone được SKU hỗ trợ

Tiếp tục đọc danh mục hai SKU, lần này lấy danh sách zone trong region:

```bash
az vm list-skus \
  --location southeastasia \
  --resource-type virtualMachines \
  --size Standard_B2 \
  --all \
  --query "[?name=='Standard_B2ls_v2' || name=='Standard_B2als_v2'].{Name:name,Zones:locationInfo[?location=='southeastasia'].zones[]}" \
  --output json
```

`Zones` là danh sách zone hỗ trợ được SKU metadata trả về cho `southeastasia`; `--all` vẫn bao gồm SKU/zone có restriction. Đối chiếu danh sách này với restriction ở mục 4.3, không coi toàn bộ zone hiển thị là đã được phép dùng. Ví dụ, nếu SKU báo `[1,2,3]` và restriction chỉ báo Zone 2, Zone 1 và 3 là ứng viên để kiểm tra tiếp, còn Zone 2 bị hạn chế theo kết quả hiện tại.

Availability Zone có vai trò tương tự AZ của AWS. Zone number là nhãn logical trong subscription, không phải tên subnet. Chọn zone cho VM cũng cần tương thích với tài nguyên đi kèm như đĩa và Public IP. Bước này chỉ thu thập thông tin; quyết định region/zone/size và giá được ghi nhận khi hoàn tất kiểm tra. Không coi việc bỏ cấu hình zone là cách chắc chắn vượt restriction.

Tài liệu tham chiếu: [SKU restrictions](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-sku-not-available), [Resource SKU location info](https://learn.microsoft.com/en-us/rest/api/compute/resource-skus/list?view=rest-compute-2021-07-01), [Availability Zones](https://learn.microsoft.com/en-us/azure/reliability/availability-zones-overview).

Kết quả thực tế: cả `Standard_B2als_v2` và `Standard_B2ls_v2` trả danh sách zone gồm `1`, `2`, `3` tại `southeastasia`; thứ tự trong array khác nhau không đổi ý nghĩa tập zone. Kết hợp restriction đã ghi ở mục 4.3, Zone 1 và 3 là ứng viên kiểm tra tiếp, Zone 2 đang bị hạn chế. Chưa có bằng chứng tạo VM thành công.

### 4.5. Đối chiếu giá compute của hai ứng viên

Giá retail được đọc ngày 2026-11-06 từ Azure Retail Prices API cho region `southeastasia`, tiền tệ USD, Linux VM thông thường theo consumption. Chọn record `productName=Virtual Machines Basv2 Series` hoặc `Virtual Machines Bsv2 Series`, với `skuName` cơ bản tương ứng; các record Windows, Cloud Services, Spot hoặc Low Priority là sản phẩm/kiểu giá khác.

| VM size | USD/giờ compute | 100 giờ | 730 giờ |
|---|---|---|---|
| Standard_B2als_v2 | 0.0472 | 4.72 USD | 34.46 USD |
| Standard_B2ls_v2 | 0.0528 | 5.28 USD | 38.54 USD |

Công thức: chi phí compute ước tính = đơn giá theo giờ × số giờ tính phí. 730 giờ chỉ là mốc so sánh tháng, không phải thời lượng được chốt cho lab. Các số trên chưa gồm Managed Disk, Public IP, lưu lượng mạng, thuế hoặc điều chỉnh theo offer. Giá và cách áp dụng credit cần đối chiếu lại tại thời điểm triển khai.

Nguồn dữ liệu: [truy vấn Azure Retail Prices](https://prices.azure.com/api/retail/prices?%24filter=serviceName+eq+%27Virtual+Machines%27+and+armRegionName+eq+%27southeastasia%27+and+%28armSkuName+eq+%27Standard_B2als_v2%27+or+armSkuName+eq+%27Standard_B2ls_v2%27%29&currencyCode=USD). Cách dùng API: [Microsoft Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices).

Ứng viên ưu tiên về giá compute là `Standard_B2als_v2` (2 vCPU, 4 GiB RAM, x86-64), với Zone 1 làm phương án khảo sát. Đây chưa phải quyết định apply; cần hoàn tất kiểm tra policy, cấu hình tài nguyên đi kèm và tổng chi phí. Chọn Standard SSD cho lab sau khi kiểm tra minimum OS image và giá đĩa; không suy ra hiệu năng workload chỉ từ số CPU/RAM.

Để tự đối chiếu bằng giao diện, mở [Azure Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/), thêm Virtual Machines, chọn region Southeast Asia, Linux, size tương ứng, Pay as you go, một instance và nhập số giờ. Tiếp tục cộng đĩa và IP khi xác định được cấu hình của chúng. Mở calculator không tạo tài nguyên cloud.

### 4.6. Đọc policy assignment áp dụng tại subscription

Trong Git Bash, dùng subscription mặc định đã xác nhận:

```bash
az policy assignment list \
  --filter "atScope()" \
  --disable-scope-strict-match true \
  --output json
```

`atScope()` yêu cầu các assignment áp dụng tại scope subscription; `--disable-scope-strict-match true` cho phép CLI giữ cả kết quả kế thừa từ scope cha. Không đặt scope khác thì CLI sử dụng subscription đang chọn. Lệnh chỉ đọc thông tin.

Các trường cần đọc trong kết quả:

- `displayName`/`name`: tên assignment.
- `policyDefinitionId`: policy hoặc bộ policy được áp dụng.
- `scope` và `notScopes`: phạm vi được áp dụng và phạm vi loại trừ.
- `parameters`: giá trị cấu hình, ví dụ danh sách region hoặc SKU.
- `enforcementMode`: chế độ thực thi của assignment.

Nếu có policy về Allowed locations hoặc Allowed VM SKUs, đối chiếu `southeastasia` và `Standard_B2als_v2` với cấu hình thực tế. Tên assignment chỉ giúp nhận diện; cần đọc definition/effect khi chưa rõ ý nghĩa parameters. Bổ sung lệnh đọc definition sau khi xác định assignment cụ thể.

Kết quả `[]` chỉ có nghĩa truy vấn không trả assignment tại scope/quyền đọc hiện tại; chưa chứng minh platform không có giới hạn offer hoặc mọi cấu hình chắc chắn triển khai được. Nếu lệnh báo lỗi quyền, xử lý lỗi đó trước khi diễn giải danh sách policy.

Tài liệu chính thức: [az policy assignment list](https://learn.microsoft.com/en-us/cli/azure/policy/assignment#az-policy-assignment-list) và [RequestDisallowedByPolicy](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-policy-requestdisallowedbypolicy).

Kết quả đã đọc từ subscription:

| Assignment | Cấu hình/ý nghĩa ghi nhận |
|---|---|
| `sys.regionrestriction` | Allowed resource deployment regions; danh sách gồm `southeastasia`, `koreacentral`, `eastasia`, `japaneast`, `japanwest` |
| `sys.mfa-write` | Effect mặc định `Audit`; có override `Deny` cho `centraluseuap`, `eastus2euap`, `westcentralus` |
| `sys.mfa-delete` | Effect `DenyAction`; thông báo yêu cầu xác thực MFA khi quản lý tài nguyên |
| `SecurityCenterBuiltIn` | Assignment ASC Default; description mô tả bộ policy audit của Security Center |

`southeastasia` có trong `listOfAllowedLocations`, nên phù hợp danh sách region của assignment đã đọc. Chưa thấy assignment giới hạn VM SKU cụ thể trong kết quả truy vấn này. Phương án khảo sát tiếp tục là `Standard_B2als_v2` tại Southeast Asia, logical Zone 1; tính khả dụng cuối cùng còn cần xác nhận khi triển khai.

Đối với `sys.mfa-write`, đọc cả override thay vì kết luận từ effect mặc định hoặc tên policy. Danh sách override Deny được trả về không chứa `southeastasia`; Audit ghi nhận không tuân thủ nhưng không tự chặn request. `sys.mfa-delete` có thông báo yêu cầu phiên đăng nhập xác thực MFA; assignment này không có nghĩa mọi thao tác xóa đều bị cấm. Khi đánh giá một request cụ thể còn cần điều kiện trong definition và ngữ cảnh xác thực.

Ý nghĩa effect: [Audit](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/effect-audit), [DenyAction](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/effect-deny-action), [assignment overrides](https://learn.microsoft.com/en-us/azure/governance/policy/concepts/assignment-structure#overrides).

### 4.7. Tạo budget và cảnh báo chi phí

Budget là ngưỡng theo dõi chi phí theo chu kỳ. Cấu hình email trong bước này gửi cảnh báo khi chi phí đạt ngưỡng; không tự dừng VM. Budget không phải số dư credit và việc tạo budget không trừ trước số tiền đó khỏi credit. Xem [cost alerts](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/cost-mgt-alerts-monitor-usage-spending).

Trong Azure Portal, mở Subscriptions → Azure for Students → Budgets (có thể nằm dưới Cost Management) → Add. Kiểm tra scope đúng subscription. Cấu hình khởi đầu cho lab:

| Trường | Giá trị |
|---|---|
| Name | `mcf-azure-monthly` |
| Reset period | Monthly |
| Start date | Ngày đầu tháng hiện tại |
| Expiration date | Chọn sau khoảng thời gian thực hành dự kiến, ví dụ 3 tháng |
| Budget amount | 20, khi đơn vị hiển thị là USD |
| Filters | Để trống để theo dõi toàn subscription |

Nếu currency khác USD, quy đổi mức ngân sách trước khi nhập số; không mặc định 20 có nghĩa là 20 USD ở mọi billing scope.

Chọn Next và thêm các ngưỡng:

| Type | Threshold | Chi phí tương ứng với budget 20 USD |
|---|---|---|
| Actual | 50% | 10 USD |
| Actual | 80% | 16 USD |
| Actual | 100% | 20 USD |

Điền email người quản trị muốn nhận thông báo trong Alert recipients. Email nhập trực tiếp trong portal, không lưu vào tài liệu công khai. Bước này sử dụng email budget alert; không cần tạo Action Group. Kiểm tra rồi chọn Create. Xác nhận budget xuất hiện với đúng scope, amount, chu kỳ, thresholds và email nhận.

Monthly theo dõi chi phí cả chu kỳ tháng, gồm chi phí phát sinh trước ngày tạo budget. Dữ liệu chi phí thường trễ 8–24 giờ; budget được đánh giá định kỳ hằng ngày, nên đây không phải cơ chế giới hạn tức thời. Với subscription mới, một số tính năng Cost Management có thể cần đến 48 giờ để sẵn sàng. Xem [tạo và quản lý budget](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/tutorial-acm-create-budgets).

Credit còn lại và hạn sử dụng tiếp tục theo dõi riêng qua Sponsorships/Education Hub. Xem [theo dõi chi phí Azure for Students](https://learn.microsoft.com/en-us/azure/education-hub/navigate-costs). Mức 20 USD là ngưỡng cảnh báo khởi đầu của lab, không phải tổng chi phí đã nghiệm thu hoặc cơ chế bảo đảm không vượt ngân sách.

### 4.8. Chuẩn bị SSH key cho máy chủ Linux

Trong Git Bash, dùng thư mục SSH của người quản trị ngoài repository. Nếu đã có `~/.ssh/mcf-lab` hoặc `~/.ssh/mcf-lab.pub`, kiểm tra và tái sử dụng cặp phù hợp hoặc chọn tên khác; không ghi đè key đang được sử dụng.

Tạo cặp key mới:

```bash
mkdir -p ~/.ssh
ssh-keygen -t ed25519 -C "multi-cloud-failover" -f ~/.ssh/mcf-lab
```

- `-t ed25519`: thuật toán key.
- `-C`: comment nhận diện, không phải mật khẩu hoặc tài khoản cloud.
- `-f`: tên file private key; public key tự thêm đuôi `.pub`.

Khi được hỏi passphrase, đặt mật khẩu bảo vệ private key và nhập lại để xác nhận. Terminal không hiển thị ký tự khi nhập. Khi dùng SSH, client có thể hỏi passphrase; sử dụng ssh-agent nếu cần tái sử dụng key đã mở khóa trong phiên làm việc ở các bước sau.

Hai file đầu ra:

| File | Vai trò |
|---|---|
| `~/.ssh/mcf-lab` | Private key giữ trên máy quản trị |
| `~/.ssh/mcf-lab.pub` | Public key dùng khi cấu hình VM |

Kiểm tra public key bằng fingerprint:

```bash
ssh-keygen -lf ~/.ssh/mcf-lab.pub
```

Kết quả cần có fingerprint `SHA256:...` và loại `(ED25519)`. Không cần in hoặc chia sẻ nội dung private key. Thư mục `~/.ssh` thuộc máy quản trị, không đặt trong repository. Bước này tạo key local; chưa cấu hình key lên máy chủ cloud.

Đã xác nhận hai file `~/.ssh/mcf-lab` và `~/.ssh/mcf-lab.pub` tồn tại; fingerprint public key được đọc thành công với loại ED25519, độ dài 256 bit. Chưa nghiệm thu SSH tới VM vì chưa triển khai máy chủ.

## 5. Bắt đầu Terraform phía AWS

### 5.1. Xác nhận công cụ và danh tính AWS

Thực hiện trong Git Bash tại repository:

```bash
cd /d/multi-cloud-failover
terraform version
aws --version
aws configure list-profiles
```

Terraform đọc cấu hình hạ tầng và sử dụng AWS provider để gọi AWS API. AWS CLI được dùng để kiểm tra phiên xác thực trên máy quản trị; Terraform không thực thi mọi thao tác bằng cách gọi lệnh `aws`.

Profile là một bộ cấu hình AWS CLI được đặt tên, có thể chứa cấu hình đăng nhập, role và region. Một profile không đồng nghĩa với một AWS account: nhiều profile có thể trỏ tới cùng account với các quyền khác nhau.

Kiểm tra danh tính của bộ credentials đang được chọn:

```bash
aws sts get-caller-identity --output json --no-cli-pager
```

Kết quả minh họa, không phải danh tính đã nghiệm thu:

```json
{
  "UserId": "AIDAEXAMPLE",
  "Account": "123456789012",
  "Arn": "arn:aws:iam::123456789012:user/mcf-operator"
}
```

- `Account`: account sẽ được kiểm tra trước khi triển khai.
- `Arn`: IAM user hoặc role đang thực hiện request.
- `UserId`: định danh của principal; với phiên role có thể kèm tên session.

Nếu sử dụng named profile thay vì cấu hình đang được chọn, thay `TEN_PROFILE` bằng tên thực tế trong kết quả `list-profiles`:

```bash
aws sts get-caller-identity --profile TEN_PROFILE --output json --no-cli-pager
```

Credentials từ biến môi trường có thể ảnh hưởng danh tính của lệnh chạy không có `--profile`; kiểm tra kết quả STS thay vì suy ra account chỉ từ tên profile. Khi bắt đầu cấu hình provider, thống nhất cách chọn credentials cho cả CLI và Terraform.

STS thành công xác nhận phiên xác thực hoạt động, chưa chứng minh có quyền tạo VPC, EC2 hoặc các tài nguyên khác. Nếu gặp `Unable to locate credentials`, token hết hạn hoặc lỗi xác thực khác, xử lý phương thức đăng nhập trước khi chuyển sang cấu hình provider. Không đưa access key, secret key, session token hoặc nội dung file credentials vào repository hay tài liệu.

Bước này chỉ đọc thông tin, chưa tạo tài nguyên AWS. Đã xác nhận Terraform CLI 1.16.5 và AWS CLI 2.35.21 hoạt động trong Git Bash, có profile `default`; người quản trị xác nhận STS trả về đúng danh tính tài khoản dùng cho project. Không ghi account ID hoặc ARN thực tế vào tài liệu công khai. Quyền tạo tài nguyên chưa được nghiệm thu.

Tham khảo: [AWS CLI profiles và thứ tự cấu hình](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html), [STS GetCallerIdentity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html).

### 5.2. Tạo root module AWS và khai báo phiên bản

Trong Git Bash, tạo thư mục cấu hình AWS và file đầu tiên:

```bash
cd /d/multi-cloud-failover
mkdir -p deploy/terraform/aws
touch deploy/terraform/aws/versions.tf
```

Ghi vào `deploy/terraform/aws/versions.tf`:

```hcl
terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}
```

| Cấu hình | Ý nghĩa |
|---|---|
| `terraform` | Khai báo yêu cầu và thiết lập cho Terraform |
| `required_version` | Project chấp nhận Terraform CLI từ 1.10.0 đến trước 2.0.0; bản 1.16.5 đáp ứng |
| `required_providers` | Khai báo các provider mà root module cần sử dụng |
| `aws` | Tên cục bộ của provider trong cấu hình |
| `source = "hashicorp/aws"` | Provider AWS do HashiCorp phát hành trên Terraform Registry |
| `version = "~> 6.0"` | Cho phép provider từ 6.0.0 đến trước 7.0.0; bao gồm các bản minor 6.x |

Terraform CLI và AWS provider là hai phần mềm có phiên bản riêng. AWS CLI cũng là một công cụ riêng; phiên bản AWS CLI 2.x không quyết định phiên bản provider.

`versions.tf` là tên file theo quy ước để dễ tìm cấu hình phiên bản. Terraform đọc các file `.tf` trong cùng thư mục root module; tên file không tạo thứ tự thực thi. Khi chạy Terraform cho AWS, dùng thư mục `deploy/terraform/aws/` làm thư mục làm việc.

`required_providers` khai báo provider cần dùng. Block `provider "aws"` ở bước sau sẽ cấu hình region và cách chọn tài khoản cho provider đó.

Định dạng file vừa viết từ thư mục gốc repository:

```bash
terraform -chdir=deploy/terraform/aws fmt
```

`fmt` chỉ định dạng cấu hình local. Chưa chạy `init`, `plan` hoặc `apply` ở bước này. Khi đến bước `init`, Terraform tải provider và tạo `.terraform.lock.hcl` để ghi phiên bản provider đã chọn cùng checksum; lock file sẽ được commit. Thư mục `.terraform/` và file state không được commit; `.gitignore` hiện có các quy tắc tương ứng.

Tham khảo: [terraform block](https://developer.hashicorp.com/terraform/language/block/terraform), [provider requirements](https://developer.hashicorp.com/terraform/language/providers/requirements), [dependency lock file](https://developer.hashicorp.com/terraform/language/files/dependency-lock).

Chỉ đánh dấu bước tạo file hoàn thành sau khi đã ghi cấu hình và định dạng thành công trên máy quản trị.

### 5.3. Cấu hình AWS provider

Tạo file cấu hình provider từ thư mục gốc repository:

```bash
cd /d/multi-cloud-failover
touch deploy/terraform/aws/providers.tf
```

Ghi vào `deploy/terraform/aws/providers.tf`:

```hcl
provider "aws" {
  region  = "ap-southeast-1"
  profile = "default"
}
```

- `provider "aws"`: cấu hình provider có tên cục bộ `aws`, đã khai báo trong `required_providers`.
- `region`: chọn AWS Asia Pacific (Singapore), mã `ap-southeast-1`, làm region khởi đầu cho hạ tầng AWS của lab. Cấu hình này chưa xác nhận quota hoặc khả năng cấp EC2; kiểm tra trước khi tạo máy chủ.
- `profile`: chọn profile `default` trên máy quản trị, tương ứng profile đã dùng kiểm tra STS. Provider đọc cấu hình xác thực của profile; không điền access key hay secret key vào file Terraform.

Region được khai báo trực tiếp trong provider nên không phụ thuộc region mặc định của profile. Giá trị region và profile được ghi trực tiếp ở bước đầu để làm rõ cơ chế; việc chuyển sang input variables được thực hiện ở bước riêng.

`versions.tf` khai báo nguồn và ràng buộc phiên bản provider; `providers.tf` cấu hình cách sử dụng provider. Hai file cùng thư mục nên thuộc cùng root module; không cần import file này vào file kia.

Định dạng từ thư mục gốc repository:

```bash
terraform -chdir=deploy/terraform/aws fmt
```

Nếu file đã đúng định dạng, lệnh có thể không in gì. `fmt` chỉ xử lý định dạng local, chưa tải provider và chưa kiểm tra credentials hoặc quyền tạo tài nguyên. Bước tiếp theo là `terraform init` và giải thích các file khởi tạo trước khi khai báo tài nguyên.

Tham khảo: [AWS provider — xác thực và cấu hình](https://registry.terraform.io/providers/hashicorp/aws/latest/docs#authentication-and-configuration).

### 5.4. Khởi tạo thư mục làm việc và kiểm tra cấu hình

Từ thư mục gốc repository, chạy:

```bash
terraform -chdir=deploy/terraform/aws init
```

Terraform đọc yêu cầu trong `versions.tf`, khởi tạo backend và tải AWS provider phù hợp với ràng buộc `~> 6.0`. Khi chưa có lock file, Terraform chọn phiên bản phù hợp mới nhất có sẵn; khi có lock file hợp lệ, các lần init thông thường tái sử dụng phiên bản đã khóa. Không dùng `-upgrade` trong bước khởi tạo này.

Provider được tải cho nền tảng của máy chạy Terraform, hiện là Windows AMD64. Điều này độc lập với hệ điều hành Ubuntu sẽ chạy trên EC2.

Kết quả thành công có thông báo:

```text
Terraform has been successfully initialized!
```

Phiên bản provider cụ thể phụ thuộc kết quả cài đặt và được lưu trong `.terraform.lock.hcl`; ghi nhận từ kết quả thực tế, không suy ra từ phiên bản Terraform CLI.

Các thành phần trong `deploy/terraform/aws/`:

| Thành phần | Vai trò | Quản lý bằng Git |
|---|---|---|
| `versions.tf` | Yêu cầu Terraform CLI và provider | Commit |
| `providers.tf` | Region và profile của AWS provider | Commit |
| `.terraform/` | Provider đã tải và dữ liệu làm việc nội bộ | Ignore |
| `.terraform.lock.hcl` | Phiên bản provider đã chọn cùng checksum xác minh gói | Commit |

Lock file được Terraform tạo tự động; không tự viết hoặc sao chép checksum. Chia sẻ lock file giúp những người cùng project sử dụng cùng phiên bản provider. `.terraform/` có thể được tạo lại bằng `init`; không cần đưa provider binary vào repository.

Cấu hình hiện chưa có block backend nên dùng backend `local` mặc định. Khi state được ghi, vị trí mặc định là `deploy/terraform/aws/terraform.tfstate` trong workspace `default`. State ghi ánh xạ tài nguyên Terraform với tài nguyên thực trên cloud và các thuộc tính đã biết; khác với lock file ghi phiên bản provider. `init` ở bước này không bảo đảm đã sinh file state. File state được `.gitignore` loại khỏi Git; cách bảo quản state khi triển khai sẽ được hướng dẫn trước lần apply đầu tiên.

Sau khi `init` thành công, chạy riêng:

```bash
terraform -chdir=deploy/terraform/aws validate
```

Kết quả mong đợi:

```text
Success! The configuration is valid.
```

`validate` kiểm tra cấu hình và tính nhất quán theo schema provider; không xác nhận credentials, quyền IAM, quota, khả năng cấp EC2 hoặc tài nguyên cloud thực tế. Cấu hình lúc này chỉ có yêu cầu phiên bản và provider; việc validate thành công chưa phải nghiệm thu hạ tầng.

Hai lệnh trong bước này không tạo VPC, EC2 hoặc tài nguyên AWS. Chỉ đánh dấu hoàn thành khi có kết quả thực tế từ cả `init` và `validate`.

Đã xác nhận `init` và `validate` thành công. Lock file được đọc và ghi nhận AWS provider `6.72.0`, ràng buộc `~> 6.0`.

Tham khảo: [terraform init](https://developer.hashicorp.com/terraform/cli/commands/init), [dependency lock file](https://developer.hashicorp.com/terraform/language/files/dependency-lock), [local backend](https://developer.hashicorp.com/terraform/language/backend/local), [terraform validate](https://developer.hashicorp.com/terraform/cli/commands/validate).

### 5.5. Khai báo VPC và đọc plan đầu tiên

Từ thư mục gốc repository, tạo file cấu hình mạng:

```bash
touch deploy/terraform/aws/network.tf
```

Ghi vào `deploy/terraform/aws/network.tf`:

```hcl
resource "aws_vpc" "primary" {
  cidr_block           = "10.29.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name    = "mcf-aws-vpc"
    Project = "multi-cloud-failover"
  }
}
```

| Thành phần | Ý nghĩa |
|---|---|
| `resource` | Khai báo một tài nguyên Terraform quản lý |
| `aws_vpc` | Loại tài nguyên do AWS provider cung cấp |
| `primary` | Tên cục bộ trong Terraform; địa chỉ tài nguyên là `aws_vpc.primary` |
| `cidr_block` | Dải địa chỉ IPv4 của VPC AWS; Azure dự kiến dùng `10.30.0.0/16` riêng |
| `enable_dns_support` | Cho phép sử dụng DNS resolver do AWS cung cấp trong VPC |
| `enable_dns_hostnames` | Bật hỗ trợ DNS hostname; EC2 có public IPv4 có thể nhận public DNS hostname khi DNS support cũng bật |
| `tags.Name` | Tên hiển thị `mcf-aws-vpc` trên AWS Console |
| `tags.Project` | Nhãn nhận diện tài nguyên thuộc project |

`primary` trong địa chỉ Terraform là tên cục bộ, không phải VPC ID và không tự cấu hình vai trò primary của PostgreSQL. VPC ID thật dạng `vpc-...` sẽ do AWS cấp khi tạo tài nguyên. Bước này chưa có subnet, Internet Gateway hoặc máy chủ.

Định dạng rồi kiểm tra cấu hình:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công, xem thay đổi dự kiến:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Với cấu hình mới chỉ khai báo VPC như trên và chưa có tài nguyên trong state, kết quả mong đợi có:

```text
# aws_vpc.primary will be created
...
Plan: 1 to add, 0 to change, 0 to destroy.
```

- Dấu `+` biểu thị tạo mới.
- `1 to add` là một resource Terraform dự định tạo.
- `0 to change` và `0 to destroy` nghĩa là không có resource trong state cần cập nhật hoặc xóa.
- `(known after apply)` cho biết thuộc tính, ví dụ VPC ID, chỉ có giá trị sau khi tạo.

AWS tự tạo một số thành phần mặc định đi kèm VPC, như default route table, network ACL và security group. Chúng không làm tăng số resource Terraform được khai báo trong plan này. Các tài nguyên đã tồn tại ngoài state không tự được Terraform nhận quản lý.

`plan` có thể gọi AWS API để đọc và kiểm tra thông tin nhưng không thực hiện các thay đổi được đề xuất. Plan thành công chưa bảo đảm có đủ quyền thực hiện mọi thao tác tạo tài nguyên. Ở bước này chỉ đọc plan; chưa chạy `apply`. Vì chưa thêm hoặc đổi provider/backend/module, không cần chạy lại `init` chỉ để thêm resource VPC.

Tham khảo: [aws_vpc](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc), [terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan).

Đã đối chiếu kết quả plan đầu tiên: `aws_vpc.primary` được đề xuất tạo tại `ap-southeast-1`, CIDR `10.29.0.0/16`, hai tùy chọn DNS bằng `true`, tags `Name=mcf-aws-vpc` và `Project=multi-cloud-failover`. Tổng kết đúng `Plan: 1 to add, 0 to change, 0 to destroy.` Chưa chạy apply; chưa nghiệm thu VPC tồn tại trên AWS.

### 5.6. Khai báo subnet và tham chiếu VPC

Giữ nguyên block VPC trong `deploy/terraform/aws/network.tf`, thêm block sau bên dưới:

```hcl
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.primary.id
  cidr_block              = "10.29.1.0/24"
  map_public_ip_on_launch = false

  tags = {
    Name    = "mcf-aws-public-subnet"
    Project = "multi-cloud-failover"
  }
}
```

| Cấu hình | Ý nghĩa |
|---|---|
| `aws_subnet.public` | Địa chỉ resource subnet trong Terraform |
| `vpc_id = aws_vpc.primary.id` | Tham chiếu ID của VPC trong cùng root module |
| `cidr_block` | Dải subnet nằm trong CIDR `10.29.0.0/16` của VPC |
| `map_public_ip_on_launch = false` | Subnet không tự cấp public IPv4 cho instance mới; Elastic IP của máy chủ sẽ được cấu hình riêng |

`aws_vpc.primary.id` là biểu thức tham chiếu, không đặt trong dấu nháy. Terraform suy ra subnet phụ thuộc VPC từ biểu thức này: khi apply cấu hình mới, tạo VPC, nhận VPC ID rồi dùng ID đó để tạo subnet. Không cần điền sẵn `vpc-...`, không cần tạo VPC thủ công và không cần thêm `depends_on` cho quan hệ đã thể hiện bằng tham chiếu.

VPC ID chưa biết khi plan không ngăn Terraform lập kế hoạch tạo subnet. Trong plan, `vpc_id = (known after apply)` là kết quả bình thường.

Mỗi subnet AWS nằm trong một Availability Zone. Đoạn cấu hình này chưa chỉ định AZ nên AWS chọn một AZ khi tạo subnet; subnet không trải trên nhiều AZ. Khả năng cấp loại EC2 trong AZ thực tế cần kiểm tra trước bước máy chủ.

Tên `public` và tag `mcf-aws-public-subnet` diễn tả mục đích sử dụng. Subnet chỉ trở thành public khi route table hiệu lực có route trực tiếp đến Internet Gateway. Bước này chưa khai báo gateway và route đó. Cờ tự cấp public IP cũng không quyết định subnet là public hay private.

Từ thư mục gốc repository, định dạng và kiểm tra:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công, chạy:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Với hai resource hiện có trong code và chưa apply, kết quả mong đợi:

```text
# aws_subnet.public will be created
# aws_vpc.primary will be created
...
Plan: 2 to add, 0 to change, 0 to destroy.
```

Đây là tổng thay đổi so với state: VPC và subnet đều chưa được tạo nên cả hai cùng xuất hiện. Thứ tự liệt kê trong plan không phải thứ tự thực thi; Terraform dựa trên quan hệ phụ thuộc. Tiếp tục chỉ đọc plan, chưa chạy apply.

Tham khảo: [aws_subnet](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/subnet), [Terraform references và dependency](https://developer.hashicorp.com/terraform/language/expressions/references), [AWS subnet và phân loại theo routing](https://docs.aws.amazon.com/vpc/latest/userguide/configure-subnets.html).

Đã đối chiếu plan gồm `aws_vpc.primary` và `aws_subnet.public`: VPC CIDR `10.29.0.0/16`, subnet CIDR `10.29.1.0/24`, region `ap-southeast-1`, subnet không tự cấp public IPv4. `vpc_id` và Availability Zone của subnet hiển thị `(known after apply)` đúng với cấu hình. Tổng kết `Plan: 2 to add, 0 to change, 0 to destroy.` Chưa chạy apply và chưa nghiệm thu tài nguyên trên AWS.

### 5.7. Khai báo Internet Gateway

Giữ nguyên VPC và subnet trong `deploy/terraform/aws/network.tf`, thêm block:

```hcl
resource "aws_internet_gateway" "primary" {
  vpc_id = aws_vpc.primary.id

  tags = {
    Name    = "mcf-aws-igw"
    Project = "multi-cloud-failover"
  }
}
```

`aws_internet_gateway.primary` là địa chỉ resource Internet Gateway trong Terraform. Thuộc tính `vpc_id` vừa chỉ định VPC vừa yêu cầu provider gắn gateway vào VPC đó; không thêm một resource attachment riêng cho cùng liên kết.

Gateway gắn ở cấp VPC, không gắn trực tiếp vào subnet. Biểu thức `aws_vpc.primary.id` khiến gateway phụ thuộc VPC. Subnet và gateway cùng phụ thuộc VPC, nhưng ở cấu hình hiện tại không phụ thuộc lẫn nhau.

Internet Gateway cung cấp đích cho route đi Internet. Chỉ gắn gateway chưa đủ để subnet có đường ra Internet: bước sau cần route table với route `0.0.0.0/0` đến gateway và liên kết route table đó với subnet. EC2 dùng IPv4 cũng cần public IPv4 hoặc Elastic IP cùng quy tắc mạng cho phép lưu lượng tương ứng. Elastic IP và Security Group được hướng dẫn riêng.

Từ thư mục gốc repository, chạy định dạng và kiểm tra:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công, xem plan:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Với ba resource hiện có và chưa apply, kết quả mong đợi:

```text
# aws_internet_gateway.primary will be created
# aws_subnet.public will be created
# aws_vpc.primary will be created
...
Plan: 3 to add, 0 to change, 0 to destroy.
```

Tiếp tục kiểm tra đúng CIDR, region và tags của các resource. `vpc_id` của gateway hiển thị `(known after apply)` vì VPC chưa được tạo. Bước này chưa chạy apply.

Tham khảo: [aws_internet_gateway](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/internet_gateway), [AWS Internet Gateway và điều kiện kết nối](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Internet_Gateway.html).

Đã đối chiếu plan gồm `aws_internet_gateway.primary`, `aws_subnet.public` và `aws_vpc.primary`, đều tại `ap-southeast-1`. Gateway có tag `Name=mcf-aws-igw`; VPC và subnet giữ nguyên cấu hình đã kiểm tra. Tổng kết `Plan: 3 to add, 0 to change, 0 to destroy.` Chưa chạy apply; chưa khai báo route table và liên kết subnet cho đường ra Internet.

### 5.8. Khai báo route table và liên kết subnet

Giữ nguyên các resource trong `deploy/terraform/aws/network.tf`, thêm hai block sau:

```hcl
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.primary.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.primary.id
  }

  tags = {
    Name    = "mcf-aws-public-rt"
    Project = "multi-cloud-failover"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}
```

`aws_route_table.public` tạo route table thuộc VPC. Block `route` bên trong thêm default IPv4 route, chuyển traffic có đích không khớp route cụ thể hơn đến Internet Gateway. `0.0.0.0/0` là mọi địa chỉ IPv4 đích, không phải dải IP cấp cho subnet.

AWS tự thêm local route của VPC. Với cấu hình này, các route chính sau khi tạo là:

| Destination | Target | Vai trò |
|---|---|---|
| `10.29.0.0/16` | `local` | Định tuyến trong VPC; AWS tự thêm |
| `0.0.0.0/0` | Internet Gateway | Default route do cấu hình Terraform khai báo |

AWS chọn route khớp cụ thể nhất. Traffic tới `10.29.1.20` khớp local `/16`, nên không đi qua Internet Gateway chỉ vì cũng khớp `/0`.

`aws_route_table_association.public` liên kết subnet với route table vừa khai báo. Nếu chỉ tạo route table mà không liên kết, subnet mới vẫn sử dụng main route table của VPC theo liên kết ngầm định. Không cần sửa main route table cho thiết kế này.

Các tham chiếu tạo dependency: route table chờ VPC và gateway; association chờ subnet và route table. Không cần thêm `depends_on` cho các quan hệ đã thể hiện bằng tham chiếu. Cấu hình đang dùng inline `route` trong `aws_route_table`; không quản lý route của cùng table bằng resource `aws_route` riêng đồng thời.

Sau khi apply cấu hình này, subnet có route trực tiếp đến IGW và đáp ứng cách phân loại public subnet. Truy cập Internet từ máy chủ còn cần địa chỉ public IPv4/Elastic IP và quy tắc mạng phù hợp. `map_public_ip_on_launch` của subnet vẫn giữ `false`; Elastic IP sẽ được cấu hình riêng.

Từ thư mục gốc repository, định dạng và kiểm tra:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Với các bước trước chưa apply, kết quả mong đợi:

```text
Plan: 5 to add, 0 to change, 0 to destroy.
```

Năm resource là VPC, subnet, Internet Gateway, route table và route table association. Block `route` nằm trong resource route table nên không được đếm thành resource Terraform thứ sáu. Kiểm tra route `0.0.0.0/0` và các tham chiếu ID hiển thị `(known after apply)`. Chỉ đọc plan ở bước này, chưa chạy apply.

Tham khảo: [aws_route_table](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/route_table), [aws_route_table_association](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/route_table_association), [AWS subnet route tables](https://docs.aws.amazon.com/vpc/latest/userguide/subnet-route-tables.html).

Đã đối chiếu code và kết quả plan gồm đủ năm resource tại `ap-southeast-1`: VPC, subnet, IGW, route table và association. Route table có route `0.0.0.0/0` tham chiếu IGW; association tham chiếu đúng subnet và route table. Tổng kết `Plan: 5 to add, 0 to change, 0 to destroy.` Chưa chạy apply, chưa nghiệm thu mạng trên AWS.

Thông báo cuối plan về việc chưa dùng `-out` là thông tin, không phải lỗi: kết quả hiện tại là speculative plan, chưa lưu thành file để apply. Nếu sau đó chạy apply không kèm saved plan, Terraform lập kế hoạch lại dựa trên cấu hình và trạng thái lúc chạy. Quy trình lưu và kiểm tra plan, cùng quản lý state, sẽ được hướng dẫn trước lần apply đầu tiên.

### 5.9. Hiểu state và lưu plan của lớp mạng

Ba loại dữ liệu trong quy trình Terraform:

| Loại | Vai trò |
|---|---|
| Các file `.tf` | Mô tả cấu hình mong muốn |
| Saved plan `.tfplan` | Ghi kế hoạch thay đổi đã tính toán để có thể xem lại và apply |
| State `.tfstate` | Ghi ánh xạ địa chỉ resource trong code với tài nguyên cloud và các thuộc tính đã biết |

Ví dụ sau khi tạo VPC, state liên kết địa chỉ `aws_vpc.primary` với VPC ID thật do AWS cấp. Lần chạy tiếp theo, Terraform dùng liên kết đó để đọc đúng tài nguyên và so sánh với cấu hình. Nếu mất state, các tài nguyên trên AWS không tự biến mất, nhưng Terraform mất ánh xạ quản lý; chỉ clone code không khôi phục state đã bị Git ignore.

Lab một người quản trị hiện sử dụng backend `local` mặc định, không cần thêm block backend để bắt đầu. Trong workspace `default`, state được ghi ở `deploy/terraform/aws/terraform.tfstate` khi có cập nhật cần lưu. Backend local không có nghĩa tài nguyên được triển khai local: tài nguyên vẫn được tạo trên AWS qua provider.

Giữ state trên máy quản trị, không sửa nội dung JSON bằng tay hoặc xóa để xử lý lỗi. Sau khi triển khai, lưu bản sao cập nhật ngoài repository ở nơi được bảo vệ; `.gitignore` chỉ ngăn commit, không tạo backup. Khi cần chạy từ nhiều máy hoặc CI, cấu hình remote backend và chuyển state bằng quy trình migration riêng.

Lưu plan từ thư mục gốc repository:

```bash
terraform -chdir=deploy/terraform/aws plan -out=network.tfplan
```

`-out` là tùy chọn lưu kế hoạch vào file, không áp dụng thay đổi. Do dùng `-chdir`, file nằm tại `deploy/terraform/aws/network.tfplan`. Đây là file plan nhị phân do Terraform tạo; không tự viết nội dung vào file.

Kết quả mong đợi tiếp tục là:

```text
Plan: 5 to add, 0 to change, 0 to destroy.

Saved the plan to: network.tfplan
```

Đọc lại chính file vừa lưu:

```bash
terraform -chdir=deploy/terraform/aws show -no-color network.tfplan
```

`show` hiển thị saved plan dưới dạng văn bản; `-no-color` bỏ mã màu terminal. Kiểm tra đủ năm resource, region `ap-southeast-1`, đúng CIDR, route và tags. Chưa chạy apply ở bước này.

Nếu thay đổi code sau khi lưu plan, tạo lại và đọc lại plan trước khi triển khai thay đổi đó. Khi apply một saved plan, Terraform dùng kế hoạch trong file; việc sửa code sau đó không tự cập nhật saved plan. Saved plan cũng không bảo đảm apply luôn thành công nếu quyền hoặc trạng thái cloud thay đổi.

`.gitignore` hiện có `*.tfplan`, `*.tfstate`, `*.tfstate.*` và `.terraform/`, nên plan, state và provider đã tải không được commit. `.terraform.lock.hcl` vẫn cần commit. Plan và state có thể chứa dữ liệu nhạy cảm khi cấu hình mở rộng; lưu ngoài tài liệu công khai.

Tham khảo: [mục đích của state](https://developer.hashicorp.com/terraform/language/state/purpose), [local backend](https://developer.hashicorp.com/terraform/language/backend/local), [lưu plan bằng -out](https://developer.hashicorp.com/terraform/cli/commands/plan), [terraform show](https://developer.hashicorp.com/terraform/cli/commands/show).

### 5.10. Apply lớp mạng AWS đầu tiên

Đã đọc saved plan `network.tfplan` bằng Terraform và xác nhận năm thao tác đều là `create`, tại `ap-southeast-1`: VPC, subnet, Internet Gateway, route table và association. CIDR của VPC/subnet khớp cấu hình. Đây là kết quả kiểm tra kế hoạch, chưa phải kết quả triển khai.

Từ thư mục gốc repository, người quản trị chạy:

```bash
terraform -chdir=deploy/terraform/aws apply network.tfplan
```

Lệnh này thực hiện các thao tác trong saved plan, tạo tài nguyên thật trên AWS và ghi state local. Với saved plan, Terraform không hỏi nhập `yes` lần nữa; việc truyền file plan là chọn thực hiện kế hoạch đã kiểm tra. Không cần thêm `-auto-approve`.

Kết quả thành công mong đợi:

```text
Apply complete! Resources: 5 added, 0 changed, 0 destroyed.
```

Các ID thật như `vpc-...`, `subnet-...`, `igw-...` được AWS cấp và lưu vào state. Subnet và gateway đều phụ thuộc VPC; association chờ subnet và route table theo các tham chiếu. Chỉ có hạ tầng mạng trong saved plan này, chưa có EC2, EBS của máy chủ hay Elastic IP.

Sau khi apply thành công, liệt kê resource trong state:

```bash
terraform -chdir=deploy/terraform/aws state list
```

Kết quả mong đợi:

```text
aws_internet_gateway.primary
aws_route_table.public
aws_route_table_association.public
aws_subnet.public
aws_vpc.primary
```

`state list` đọc danh sách resource Terraform đang quản lý trong state. Để kiểm tra tiếp với trạng thái AWS, chạy plan mới, không dùng lại saved plan đã apply:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Nếu cấu hình và tài nguyên đã khớp, kết quả mong đợi:

```text
No changes. Your infrastructure matches the configuration.
```

Nếu apply lỗi giữa chừng, một số tài nguyên có thể đã tạo và đã ghi vào state. Giữ nguyên state, đọc lỗi và lập plan mới sau khi xử lý nguyên nhân; không xóa state hoặc tạo lại các tài nguyên bằng tay. Chưa đánh dấu nghiệm thu lớp mạng cho tới khi có kết quả thực tế. Sau nghiệm thu, giữ bản sao state ngoài repository ở nơi được bảo vệ theo mục 5.9.

Tham khảo: [terraform apply và saved plan mode](https://developer.hashicorp.com/terraform/cli/commands/apply), [terraform state list](https://developer.hashicorp.com/terraform/cli/commands/state/list).

Đã xác nhận kết quả thực hành: apply tạo thành công năm resource, `state list` có đủ năm địa chỉ như trên và plan mới báo `No changes. Your infrastructure matches the configuration.` Danh sách trong state local cũng đã được đối chiếu. Lớp mạng AWS được nghiệm thu; chưa có máy chủ hoặc workload cloud trong phạm vi bước này.

## 6. Theo dõi tiến độ

- [ ] Xác nhận Terraform, AWS CLI, Azure CLI và SSH chạy được trong Git Bash.
- [x] Đăng nhập Azure CLI và xác nhận Azure for Students ở trạng thái Enabled, được chọn mặc định.
- [x] Kiểm tra quyền tại subscription: xác nhận role Owner qua View my access.
- [x] Đọc quota Southeast Asia: tổng region 0/6; BS 0/4; Bsv2 và Basv2 đều 0/10.
- [x] Đọc SKU restriction: B2ls_v2 và B2als_v2 bị hạn chế tại Zone 2, chưa thấy Location restriction trong kết quả.
- [x] Đối chiếu danh sách zone của hai SKU và giá compute retail; size/zone mới ở mức ứng viên, chưa chốt triển khai.
- [x] Đọc policy assignment: Southeast Asia có trong allowed regions; ghi nhận các assignment MFA và ASC Default.
- [ ] Tạo budget tại subscription và xác nhận thresholds/email cảnh báo.
- [x] Xác thực AWS: người quản trị xác nhận STS trả về đúng danh tính tài khoản dùng triển khai.
- [x] Chuẩn bị SSH key local và kiểm tra fingerprint public key ED25519.
- [ ] Chọn region, kiểm tra khả năng cấp máy và chuẩn bị SSH key.
- [ ] Tạo cấu hình Terraform/provider và quy ước state/lock file.
- [x] Tạo `deploy/terraform/aws/versions.tf`; đã đọc và đối chiếu nội dung khai báo phiên bản.
- [x] Tạo `deploy/terraform/aws/providers.tf`; đã đọc và đối chiếu region/profile.
- [x] Chạy `terraform init` và `terraform validate` thành công cho root module AWS; AWS provider được khóa ở `6.72.0`.
- [x] Khai báo VPC AWS và kiểm tra plan đầu tiên: `1 to add, 0 to change, 0 to destroy`; chưa apply.
- [x] Khai báo subnet AWS và kiểm tra plan: `2 to add, 0 to change, 0 to destroy`; chưa apply.
- [x] Khai báo Internet Gateway và kiểm tra plan: `3 to add, 0 to change, 0 to destroy`; chưa apply.
- [x] Khai báo route table và liên kết subnet; kiểm tra plan: `5 to add, 0 to change, 0 to destroy`; chưa apply.
- [x] Lưu `network.tfplan` và đọc lại đúng plan lớp mạng trước khi apply.
- [x] Apply lớp mạng AWS: năm resource được tạo, state list đủ năm resource và plan mới báo No changes.
- [ ] Khai báo mạng và quy tắc truy cập của hai môi trường.
- [ ] Khai báo compute, địa chỉ IP và đĩa.
- [ ] Kiểm tra plan rồi triển khai các lớp hạ tầng.
- [ ] Xác nhận inventory, kết nối SSH và ghi bằng chứng nghiệm thu.

Chỉ đánh dấu hoàn thành theo kết quả thực hành. Các lệnh đăng nhập và đoạn cấu hình Terraform sẽ được bổ sung khi bắt đầu bước tương ứng.
