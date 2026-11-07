# Giai đoạn 4 — Hạ tầng AWS và Azure bằng Terraform

## 1. Mục tiêu và đầu ra

Chuẩn bị hai môi trường cloud độc lập cho mô hình AWS primary và Azure warm standby. Terraform mô tả tài nguyên hạ tầng; mỗi lớp được kiểm tra cấu hình, xem plan và xác nhận kết quả sau khi triển khai.

Điều kiện bắt đầu: đã hoàn thành [giai đoạn 3 — CI và container registry](giaidoan3_ci_va_container_registry.md), có tài khoản AWS và Azure riêng, cùng tên miền thuộc quyền quản lý.

Phạm vi nghiệm thu toàn project được theo dõi trong [yêu cầu và tiêu chí nghiệm thu](../PROJECT_REQUIREMENTS.md), gồm nội dung đề tài 29, General Deliverables và rubric. Giai đoạn này chuẩn bị hạ tầng cho hai môi trường; thí nghiệm, baseline và các số đo cloud được nghiệm thu ở giai đoạn tương ứng.

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

Terraform được giữ trong cùng repository với ứng dụng ở `deploy/terraform/`, để cấu hình hạ tầng, workload và hướng dẫn được quản lý theo cùng project. AWS sử dụng root module `deploy/terraform/aws/`; Azure sử dụng `deploy/terraform/azure/`. Mỗi root module có local state riêng cho lab một người quản trị để thao tác từng cloud độc lập; xem nguyên tắc state ở mục 5.9. Quy mô hiện tại chưa cần một repository hạ tầng riêng.

Tài liệu được bổ sung theo từng bước thực hành. Hạ tầng AWS và Azure đã được triển khai, kiểm tra post-apply plan và nghiệm thu SSH độc lập theo các mục dưới đây. Sau nghiệm thu, cả hai môi trường lab đã được dọn để tiết kiệm chi phí; giữ code và state local để tạo lại. Lập plan mới khi tiếp tục thực hành và tạo lại các máy theo nhu cầu của giai đoạn 5. Phần workload cloud được tiếp tục ở giai đoạn đó.

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
  availability_zone       = "ap-southeast-1c"
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
| `availability_zone` | Cố định subnet tại `ap-southeast-1c` trong Singapore |
| `map_public_ip_on_launch = false` | Subnet không tự cấp public IPv4 cho instance mới; Elastic IP của máy chủ sẽ được cấu hình riêng |

`aws_vpc.primary.id` là biểu thức tham chiếu, không đặt trong dấu nháy. Terraform suy ra subnet phụ thuộc VPC từ biểu thức này: khi apply cấu hình mới, tạo VPC, nhận VPC ID rồi dùng ID đó để tạo subnet. Không cần điền sẵn `vpc-...`, không cần tạo VPC thủ công và không cần thêm `depends_on` cho quan hệ đã thể hiện bằng tham chiếu.

VPC ID chưa biết khi plan không ngăn Terraform lập kế hoạch tạo subnet. Trong plan, `vpc_id = (known after apply)` là kết quả bình thường.

Mỗi subnet AWS nằm trong một Availability Zone. Khai báo `availability_zone = "ap-southeast-1c"` để vị trí được xác định rõ trong code khi tái dựng. Nếu bỏ thuộc tính này, AWS chọn một AZ khi tạo subnet; subnet không trải trên nhiều AZ. Khả năng cấp loại EC2 trong AZ đã chọn cần kiểm tra trước bước máy chủ.

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

Đã đối chiếu plan gồm `aws_vpc.primary` và `aws_subnet.public`: VPC CIDR `10.29.0.0/16`, subnet CIDR `10.29.1.0/24`, region `ap-southeast-1`, subnet không tự cấp public IPv4. `vpc_id` hiển thị `(known after apply)` vì VPC chưa được tạo. Tổng kết `Plan: 2 to add, 0 to change, 0 to destroy.` Tại thời điểm kiểm tra này chưa chạy apply; AZ được cố định rõ trong cấu hình hiện tại và kiểm tra lại ở mục 5.17.

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

### 5.11. Tạo Security Group và quy tắc outbound

Sau khi lớp mạng đã apply và plan báo No changes, bắt đầu cấu hình truy cập cho máy chủ. Từ thư mục gốc repository, tạo file:

```bash
touch deploy/terraform/aws/security.tf
```

Ghi vào `deploy/terraform/aws/security.tf`:

```hcl
resource "aws_security_group" "primary" {
  name        = "mcf-aws-host"
  description = "Traffic rules for the AWS primary host"
  vpc_id      = aws_vpc.primary.id

  tags = {
    Name    = "mcf-aws-host"
    Project = "multi-cloud-failover"
  }
}

resource "aws_vpc_security_group_egress_rule" "all_ipv4" {
  security_group_id = aws_security_group.primary.id
  description       = "Allow outbound IPv4 traffic"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
```

`aws_security_group.primary` tạo nhóm quy tắc trong VPC. `name` là tên Security Group trên AWS; `primary` là tên cục bộ trong Terraform. Nhóm sẽ được gắn với network interface của EC2 ở bước cấu hình máy chủ, không gắn với toàn bộ subnet chỉ bằng `vpc_id`.

Resource `aws_vpc_security_group_egress_rule.all_ipv4` khai báo quy tắc outbound riêng:

- `security_group_id`: tham chiếu nhóm mà quy tắc áp dụng.
- `cidr_ipv4 = "0.0.0.0/0"`: mọi địa chỉ IPv4 đích.
- `ip_protocol = "-1"`: cho phép mọi giao thức IP và mọi port; không khai báo `from_port` hoặc `to_port` khi dùng giá trị này.

Outbound cho phép máy chủ chủ động tải package, K3s và image khi các điều kiện địa chỉ, routing và DNS đã đáp ứng. AWS provider loại bỏ egress allow-all mặc định khi tạo Security Group, nên khai báo rõ rule mong muốn trong Terraform. Dùng các resource rule riêng, không trộn với inline `ingress`/`egress` của cùng Security Group.

Chưa có ingress rule cho kết nối mới từ bên ngoài, gồm SSH. Security Group là stateful: response của kết nối outbound được phép vẫn có thể quay về; không cần mở ingress tương ứng chỉ để nhận response. Quy tắc SSH theo public IPv4 của người quản trị được thêm ở bước sau.

Từ thư mục gốc repository, chạy:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công, xem plan mới:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Kết quả mong đợi, nếu năm resource mạng đã apply và không có drift:

```text
Plan: 2 to add, 0 to change, 0 to destroy.
```

Hai resource mới là Security Group và outbound rule; năm resource mạng hiện có không cần tạo lại. Plan có thể in các dòng Refreshing state cho tài nguyên cũ; đọc các action và tổng kết để phân biệt refresh với thay đổi. Bước này chỉ đọc plan, chưa apply hoặc dùng lại `network.tfplan` của lần triển khai trước.

Tham khảo: [aws_security_group](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/security_group), [aws_vpc_security_group_egress_rule](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_security_group_egress_rule), [AWS Security Group và stateful traffic](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html).

Đã xác nhận kết quả plan đúng hai resource mới theo cấu hình Security Group và outbound rule; chưa apply các resource này.

### 5.12. Khai báo biến nguồn truy cập SSH

Mỗi người quản trị cung cấp public IPv4 hiện tại làm nguồn SSH. Dùng input variable để cấu hình này không gắn cố định vào mã Security Group chung.

Từ thư mục gốc repository, tạo file khai báo biến:

```bash
touch deploy/terraform/aws/variables.tf
```

Ghi vào `deploy/terraform/aws/variables.tf`:

```hcl
variable "admin_cidr" {
  description = "Public IPv4 CIDR allowed to SSH to the AWS host"
  type        = string
}
```

`variable` khai báo một đầu vào tên `admin_cidr`. `type = string` yêu cầu giá trị chuỗi. Không khai báo `default` nên người chạy phải cung cấp giá trị khi Terraform lập plan. Cách tham chiếu trong resource ở bước sau là `var.admin_cidr`.

Trong Git Bash, đọc public IPv4 của kết nối hiện tại:

```bash
curl -4 -fsS https://checkip.amazonaws.com
```

Địa chỉ trả về là IPv4 public của đường ra Internet đang sử dụng, có thể là địa chỉ NAT của router hoặc VPN; không dùng địa chỉ LAN của laptop. Lệnh chỉ truy vấn địa chỉ, không mở port hoặc tạo resource.

Tạo file gán giá trị local:

```bash
touch deploy/terraform/aws/terraform.tfvars
```

Ghi vào `terraform.tfvars`, thay địa chỉ minh họa bằng kết quả thực tế:

```hcl
admin_cidr = "203.0.113.10/32"
```

`203.0.113.10` chỉ là địa chỉ ví dụ, không dùng để triển khai SSH thực tế. `/32` giới hạn đúng một địa chỉ IPv4 nguồn. Khi đổi mạng hoặc VPN làm public IPv4 thay đổi, cập nhật giá trị local và triển khai thay đổi rule tương ứng.

`variables.tf` khai báo tên/kiểu đầu vào và được commit. `terraform.tfvars` gán giá trị riêng của người chạy, được `.gitignore` loại khỏi Git bằng quy tắc `*.tfvars`. Terraform tự đọc file đúng tên `terraform.tfvars` trong root module được chọn bởi `-chdir`; không cần thêm `-var-file` cho file này.

Định dạng và kiểm tra từ thư mục gốc repository:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
git check-ignore -v deploy/terraform/aws/terraform.tfvars
```

Kết quả validate mong đợi là `Success! The configuration is valid.`; `check-ignore` cần hiển thị quy tắc `*.tfvars` từ `.gitignore`. Biến hiện chưa được dùng trong rule, nên bước này chưa thêm ingress hoặc resource cloud; không apply ở bước này. Không cần đưa public IP thực tế vào tài liệu công khai hoặc gửi để nghiệm thu; chỉ cần xác nhận đã điền đúng IPv4 với `/32`.

Tham khảo: [Terraform input variables và variable values](https://developer.hashicorp.com/terraform/language/values/variables), [AWS SSH source IP](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html#sg-rules-your-computer).

Đã đối chiếu khai báo `admin_cidr`, xác nhận file `terraform.tfvars` local tồn tại và được ignore theo quy tắc `*.tfvars`. Giá trị được kiểm tra đúng cú pháp IPv4 `/32`, không dùng địa chỉ ví dụ `203.0.113.0/24`; không đưa giá trị thực vào tài liệu. Việc địa chỉ còn khớp đường ra Internet được kiểm tra lại khi cần kết nối SSH.

### 5.13. Thêm ingress rule cho SSH

Giữ nguyên Security Group và outbound rule trong `deploy/terraform/aws/security.tf`, thêm:

```hcl
resource "aws_vpc_security_group_ingress_rule" "ssh" {
  security_group_id = aws_security_group.primary.id
  description       = "Allow SSH from the operator IPv4"
  cidr_ipv4         = var.admin_cidr
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
}
```

`aws_vpc_security_group_ingress_rule.ssh` là một resource rule cho kết nối vào. `security_group_id` tham chiếu nhóm đã khai báo, còn `var.admin_cidr` đọc giá trị đầu vào được gán trong `terraform.tfvars`. Biểu thức tham chiếu không đặt trong dấu nháy.

Luồng giá trị: khai báo tên/kiểu tại `variables.tf`, gán giá trị tại `terraform.tfvars`, sử dụng qua `var.admin_cidr` trong resource rule.

Trong ingress rule, `cidr_ipv4` là dải IPv4 nguồn được phép kết nối. Trong outbound rule ở mục 5.11, cùng tên thuộc tính đó biểu thị dải IPv4 đích. `ip_protocol = "tcp"` cùng `from_port = 22` và `to_port = 22` chỉ cho phép TCP đến port 22 của máy chủ khi Security Group được gắn vào máy chủ đó; hai thuộc tính port là đầu/cuối của dải port đích, không phải port nguồn/port đích của kết nối.

Từ thư mục gốc repository, chạy:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Nếu Security Group và outbound rule ở mục 5.11 chưa apply, kết quả mong đợi:

```text
Plan: 3 to add, 0 to change, 0 to destroy.
```

Ba resource mới là Security Group, outbound rule và SSH ingress rule. Năm resource mạng đã triển khai được giữ nguyên. Kiểm tra riêng phần `aws_vpc_security_group_ingress_rule.ssh`: TCP, port 22–22, nguồn đúng IPv4 `/32` đã nhập. Nếu Terraform hỏi nhập `var.admin_cidr`, kiểm tra vị trí/tên `terraform.tfvars` trong root module AWS.

Bước này chỉ kiểm tra plan, chưa apply rule. Chưa có EC2 nên chưa thực hiện kiểm tra kết nối SSH. Không dùng lại saved plan `network.tfplan` cho thay đổi mới.

Tham khảo: [aws_vpc_security_group_ingress_rule](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_security_group_ingress_rule), [AWS SSH source và port](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html#sg-rules-your-computer).

Đã xác nhận plan sau khi thêm SSH rule đúng ba resource mới. Chưa apply nhóm và các rule.

### 5.14. Thêm ingress rule HTTP và HTTPS

Giữ nguyên nội dung hiện có trong `deploy/terraform/aws/security.tf`, thêm:

```hcl
resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.primary.id
  description       = "Allow public HTTP"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.primary.id
  description       = "Allow public HTTPS"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
```

Hai rule dùng cùng cơ chế như rule SSH. HTTP cho phép kết nối TCP đến port 80, HTTPS đến port 443. `cidr_ipv4 = "0.0.0.0/0"` trong ingress cho phép mọi địa chỉ IPv4 nguồn, phù hợp endpoint web công khai. Rule SSH vẫn giữ `var.admin_cidr` để giới hạn nguồn quản trị.

| Kết nối vào | Port đích | Nguồn IPv4 |
|---|---|---|
| SSH | TCP 22 | `var.admin_cidr`, IPv4 `/32` của người quản trị |
| HTTP | TCP 80 | `0.0.0.0/0` |
| HTTPS | TCP 443 | `0.0.0.0/0` |

Khi triển khai workload, Traefik sẽ phục vụ web qua các port này; HTTP có thể chuyển hướng sang HTTPS. Health check HTTPS cũng truy cập qua port 443. Ứng dụng vẫn có thể lắng nghe port 8080 bên trong cluster mà không cần mở trực tiếp port đó qua Security Group. Tạo rule không cài web server hoặc chứng chỉ TLS; các phần đó được thực hiện ở giai đoạn workload và HTTPS.

Từ thư mục gốc repository, chạy định dạng và kiểm tra:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Nếu Security Group và các rule trước vẫn chưa apply, kết quả mong đợi:

```text
Plan: 5 to add, 0 to change, 0 to destroy.
```

Năm resource mới gồm một Security Group, một outbound rule và ba ingress rule SSH/HTTP/HTTPS. Năm resource mạng đã triển khai không cần tạo lại. Kiểm tra đúng từng port và nguồn trong plan; tiếp tục chưa apply ở bước này.

Tham khảo: [AWS web server rules](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/security-group-rules-reference.html#sg-rules-web-server), [Terraform ingress rule](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/vpc_security_group_ingress_rule).

Đã xác nhận plan đúng năm resource mới. Nội dung `security.tf` được đối chiếu và các kiểm tra `fmt -check`, `validate` đều đạt. State tại thời điểm kiểm tra vẫn chỉ có năm resource mạng; nhóm và rule chưa được apply.

### 5.15. Apply Security Group và các rule

Từ thư mục gốc repository, lưu plan mới cho lớp truy cập:

```bash
terraform -chdir=deploy/terraform/aws plan -out=security.tfplan
```

Đọc kết quả trước khi thực hiện: phải có `5 to add, 0 to change, 0 to destroy`, gồm Security Group, outbound rule và ba ingress rule SSH/HTTP/HTTPS. Kiểm tra nguồn SSH đúng IPv4 `/32` của người quản trị, nguồn web `0.0.0.0/0` và các port đúng 22, 80, 443. Plan mới được lưu tại `deploy/terraform/aws/security.tfplan` và được Git ignore.

Khi saved plan đúng, người quản trị thực hiện:

```bash
terraform -chdir=deploy/terraform/aws apply security.tfplan
```

Lệnh thực hiện kế hoạch đã lưu trên AWS, không hỏi nhập `yes` lần nữa. Không dùng saved plan `network.tfplan` đã apply ở bước trước.

Kết quả thành công mong đợi:

```text
Apply complete! Resources: 5 added, 0 changed, 0 destroyed.
```

Kiểm tra lại bằng plan mới:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Kết quả mong đợi:

```text
No changes. Your infrastructure matches the configuration.
```

Nếu cần đối chiếu danh sách quản lý:

```bash
terraform -chdir=deploy/terraform/aws state list
```

State mong đợi có tổng cộng mười resource: năm resource mạng trước đó và năm resource của lớp truy cập. Security Group tồn tại trong VPC nhưng chưa gắn với máy chủ nào, vì chưa triển khai EC2. Kết nối SSH/web thực tế được nghiệm thu sau khi có máy chủ và dịch vụ tương ứng. Giữ bản sao state cập nhật ngoài repository theo mục 5.9.

Chỉ đánh dấu bước apply thành công theo kết quả thực hành. Nếu apply lỗi, giữ nguyên state và xử lý lỗi trước khi lập plan mới.

Tham khảo: [Terraform saved plan mode](https://developer.hashicorp.com/terraform/cli/commands/apply#saved-plan-mode).

Đã đối chiếu state local sau bước triển khai: có đủ mười resource, bao gồm Security Group và bốn rule. AZ của subnet trong state là `ap-southeast-1c`, CIDR `10.29.1.0/24`. Plan sau triển khai được xác nhận No changes khi kiểm tra cấu hình cố định AZ ở mục 5.17.

### 5.16. Kiểm tra quota và EC2 offering trước khi khai báo máy chủ

Máy chủ dự kiến dùng `t3.medium` On-Demand, x86-64, hai vCPU và 4 GiB RAM để chạy K3s, PostgreSQL và ứng dụng trong lab. Đây là cấu hình ứng viên; khả năng chạy workload và số đo hiệu năng cần được kiểm tra sau khi triển khai. AMI, EBS, CPU credit mode và chi phí được đối chiếu trước bước tạo máy chủ.

Kiểm tra quota Standard On-Demand tại Singapore bằng Git Bash:

```bash
aws service-quotas get-service-quota \
  --profile default \
  --region ap-southeast-1 \
  --service-code ec2 \
  --quota-code L-1216C47A \
  --query 'Quota.{Name:QuotaName,Value:Value}' \
  --output table \
  --no-cli-pager
```

Quota `L-1216C47A` là Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances, tính bằng vCPU theo region. `Value` là giới hạn áp dụng, không phải số vCPU còn trống hoặc số máy. Một `t3.medium` cần hai vCPU trong quota này; phải trừ phần quota đang dùng bởi các instance Standard On-Demand khác. Nếu gặp AccessDenied khi đọc quota, đây là lỗi quyền truy vấn, không có nghĩa quota bằng không.

Kiểm tra những AZ trong region có offering `t3.medium`:

```bash
aws ec2 describe-instance-type-offerings \
  --profile default \
  --region ap-southeast-1 \
  --location-type availability-zone \
  --filters Name=instance-type,Values=t3.medium \
  --query 'InstanceTypeOfferings[].{Type:InstanceType,AZ:Location}' \
  --output table \
  --no-cli-pager
```

Đối chiếu với AZ của subnet trong cấu hình và state. Cấu hình hiện cố định `ap-southeast-1c`, nên cần có offering tại AZ đó trong account đang dùng. Khi tái dựng hoặc chủ động thay đổi cấu hình AZ, kiểm tra lại offering và đọc vị trí subnet bằng:

```bash
terraform -chdir=deploy/terraform/aws state show aws_subnet.public
```

EC2 đặt trong subnet sẽ nằm cùng AZ với subnet đó. Offering cho biết loại máy được cung cấp tại AZ, không bảo đảm capacity tức thời hoặc toàn bộ điều kiện account để launch. Hai lệnh AWS phía trên chỉ đọc thông tin, không tạo instance và không thay đổi quota. Chưa chạy lệnh tạo máy chủ hoặc viết resource EC2 ở bước này.

Tham khảo: [thông số EC2 general purpose](https://docs.aws.amazon.com/ec2/latest/instancetypes/gp.html), [EC2 On-Demand quotas](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html), [AWS CLI quota example và quota code](https://docs.aws.amazon.com/cli/latest/userguide/cli_service-quotas_code_examples.html), [describe-instance-type-offerings](https://docs.aws.amazon.com/cli/latest/reference/ec2/describe-instance-type-offerings.html).

Kết quả kiểm tra đã nhận tại `ap-southeast-1`:

| Hạng mục | Kết quả |
|---|---|
| Standard On-Demand quota `L-1216C47A` | 16 vCPU |
| Offering `t3.medium` | `ap-southeast-1a`, `ap-southeast-1b`, `ap-southeast-1c` |
| AZ subnet theo state | `ap-southeast-1c`, có offering phù hợp |

Giới hạn 16 vCPU lớn hơn nhu cầu hai vCPU của một `t3.medium`, nhưng chưa đối chiếu phần quota đang dùng bởi các instance khác. Không diễn giải kết quả này thành còn trống 16 vCPU hoặc bảo đảm launch thành công. Chưa triển khai EC2 ở bước kiểm tra này.

### 5.17. Cố định AZ khớp subnet đã triển khai

Subnet hiện có nằm tại `ap-southeast-1c`. Dòng cấu hình được bổ sung vào resource `aws_subnet.public` trong `network.tf`:

```hcl
availability_zone = "ap-southeast-1c"
```

Khai báo rõ AZ làm cho cấu hình tái dựng xác định vị trí subnet. Với subnet đang tồn tại đúng AZ này, thay đổi code không yêu cầu tạo lại subnet. Sau khi thêm, kiểm tra:

```bash
terraform -chdir=deploy/terraform/aws fmt -check
terraform -chdir=deploy/terraform/aws validate
terraform -chdir=deploy/terraform/aws plan
```

Kết quả plan mong đợi là `No changes. Your infrastructure matches the configuration.` Không cần apply khi plan không có thay đổi. Nếu chọn một AZ khác với subnet hiện có, Terraform có thể đề xuất thay thế subnet và tài nguyên phụ thuộc; đọc kỹ plan trước khi thực hiện.

Tham khảo: [AWS CreateSubnet — AZ mặc định](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_CreateSubnet.html), [Terraform aws_subnet](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/subnet).

Kết quả đã kiểm tra: `fmt -check` và `validate` đạt; `plan -detailed-exitcode` trả về exit code 0 với thông báo No changes. Không thực hiện apply cho thay đổi khai báo AZ này.

### 5.18. Tra cứu AMI Ubuntu bằng data source

Từ thư mục gốc repository, tạo file tra cứu dữ liệu AWS:

```bash
touch deploy/terraform/aws/data.tf
```

Ghi vào `deploy/terraform/aws/data.tf`:

```hcl
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}
```

`data` đọc thông tin đã có từ provider. `aws_ami` tìm Amazon Machine Image; `ubuntu` là tên cục bộ, cho địa chỉ data source `data.aws_ami.ubuntu`. Khác với managed resource, bước tra cứu này không tạo hoặc sao chép AMI.

| Cấu hình | Ý nghĩa |
|---|---|
| `owners` | Chỉ tìm AMI của Canonical, owner ID `099720109477` trong AWS partition đang dùng |
| Name filter | Giới hạn Ubuntu Server 24.04 Noble, AMD64, HVM và dòng image EBS gp3 |
| Architecture filter | Xác nhận `x86_64`, phù hợp instance T3 và container image Linux AMD64 |
| Virtualization filter | Chọn HVM |
| `most_recent = true` | Khi có nhiều AMI khớp, lấy bản mới nhất trong tập đã lọc |

Owner ID này là định danh công khai của nhà phát hành Canonical, không phải account ID của người triển khai. Các filter được áp dụng đồng thời, và data source sử dụng region `ap-southeast-1` của AWS provider. Tên AMI dùng `amd64`, còn trường architecture của AWS dùng `x86_64` cho cùng kiến trúc.

`most_recent` vẫn bị giới hạn bởi filter Ubuntu 24.04; không tự đổi sang bản Ubuntu khác. Kết quả AMI có thể thay đổi khi có bản phát hành mới khớp filter. Trước khi dùng cho máy chủ chứa dữ liệu, chốt cách giữ AMI đã chọn để kiểm soát việc thay thế máy chủ trong các lần cập nhật sau.

Cách lấy ID khi cấu hình máy chủ ở bước sau là `data.aws_ami.ubuntu.id`. Bước này chỉ khai báo tra cứu, chưa khai báo EC2.

Định dạng và kiểm tra:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công, chạy:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Terraform cần quyền `ec2:DescribeImages` để đọc kết quả. Khi tra cứu thành công, log thường có dòng `data.aws_ami.ubuntu: Read complete ... [id=ami-...]`. Với mười managed resource hiện tại đã khớp cấu hình và chưa có output mới, plan mong đợi tiếp tục báo `No changes. Your infrastructure matches the configuration.` Data source không được tính thành một resource AWS cần tạo mới. Nếu chưa thấy ID hoặc cần kiểm tra thêm thuộc tính, hướng dẫn đọc kết quả được bổ sung ở bước tương ứng.

Tham khảo: [Canonical — tìm và xác minh Ubuntu AMI](https://ubuntu.com/aws/docs/aws-how-to/instances/find-ubuntu-images/), [Terraform aws_ami](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ami), [Terraform data sources](https://developer.hashicorp.com/terraform/language/data-sources).

Đã đối chiếu nội dung `data.tf` và log tra cứu thành công: `data.aws_ami.ubuntu` trả về `ami-0403d346e3210afd6` tại Singapore theo các filter trên. AMI ID này là kết quả tại thời điểm kiểm tra, không phải giá trị mặc định cố định cho mọi lần dựng lại. Các dòng `Refreshing state` tiếp theo biểu thị đọc tài nguyên hiện có, không phải tạo lại chúng. Phần tổng kết cuối plan chưa có trong log được cung cấp cho bước này.

### 5.19. Khai báo EC2 Key Pair từ public key local

Tái sử dụng cặp key ED25519 đã chuẩn bị tại mục 4.8. Đã xác nhận hai file local tồn tại và đọc fingerprint public key thành công; không đọc nội dung private key. Người tái dựng project cần chuẩn bị cặp key của mình theo hướng dẫn, không dùng private key của người khác.

Từ thư mục gốc repository, tạo file cấu hình compute:

```bash
touch deploy/terraform/aws/compute.tf
```

Ghi vào `deploy/terraform/aws/compute.tf`:

```hcl
resource "aws_key_pair" "operator" {
  key_name   = "mcf-lab"
  public_key = file(pathexpand("~/.ssh/mcf-lab.pub"))

  tags = {
    Name    = "mcf-lab"
    Project = "multi-cloud-failover"
  }
}
```

`aws_key_pair.operator` đăng ký public key có sẵn lên EC2 tại region của provider khi apply. Resource này không sinh cặp key mới hoặc tải private key về. `key_name` là tên đăng ký trên AWS, còn `operator` là tên cục bộ của resource trong Terraform.

Biểu thức `file(pathexpand("~/.ssh/mcf-lab.pub"))` được đọc từ trong ra ngoài:

1. `pathexpand` thay `~` bằng thư mục home của người đang chạy Terraform.
2. `file` đọc nội dung public key ở đường dẫn đó.
3. `public_key` nhận nội dung key để gửi tới AWS khi apply.

Public key phải tồn tại trên máy chạy Terraform ngay khi đọc cấu hình. Nếu tên hoặc vị trí key khác, điều chỉnh đường dẫn tới đúng file `.pub`. Private key `~/.ssh/mcf-lab` giữ ngoài repository và không được tham chiếu trong resource.

Khi khai báo EC2 ở bước sau, dùng `aws_key_pair.operator.key_name` để chọn key. Khi khởi tạo Linux instance, public key tương ứng được đặt vào `authorized_keys` của tài khoản đăng nhập; SSH client sử dụng private key local để chứng minh danh tính. Security Group và SSH key có vai trò riêng: rule cho phép đường kết nối TCP 22 từ nguồn đã chọn, còn key dùng xác thực đăng nhập.

Định dạng và kiểm tra:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Với mười managed resource hiện có đã khớp cấu hình, kết quả mong đợi là:

```text
# aws_key_pair.operator will be created
...
Plan: 1 to add, 0 to change, 0 to destroy.
```

Data source AMI tiếp tục chỉ đọc thông tin. Bước này chưa apply Key Pair và chưa tạo EC2; kết quả plan không phải nghiệm thu kết nối SSH.

Tham khảo: [Terraform aws_key_pair](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/key_pair), [Terraform pathexpand](https://developer.hashicorp.com/terraform/language/functions/pathexpand), [AWS EC2 key pairs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html).

### 5.20. Cố định AMI đã chọn trước khi khai báo EC2

Sau bước tra cứu, dùng AMI ID đã xác nhận thay cho việc luôn chọn bản phát hành mới nhất. AMI đã đọc tại Singapore là `ami-0403d346e3210afd6`. ID AMI là thông tin image của region, không phải credential của người triển khai.

Trong `deploy/terraform/aws/data.tf`, bỏ dòng:

```hcl
most_recent = true
```

Thêm filter bên trong block `data "aws_ami" "ubuntu"`, giữ nguyên `owners` và các filter name, architecture, virtualization-type:

```hcl
filter {
  name   = "image-id"
  values = ["ami-0403d346e3210afd6"]
}
```

Các filter được kết hợp đồng thời: phải đúng ID đã chọn, do Canonical phát hành, tên Ubuntu Server 24.04 AMD64, architecture x86-64 và virtualization HVM. Data source vẫn đọc thông tin AMI và cung cấp `data.aws_ami.ubuntu.id` để resource máy chủ tham chiếu.

Sau thay đổi, việc Canonical phát hành AMI mới cùng dòng không làm kết quả tra cứu tự đổi sang ID khác. Đổi AMI về sau là thay đổi có chủ đích trong code và phải xem tác động đến máy chủ trong plan, đặc biệt khi máy chủ đã có dữ liệu PostgreSQL. Pin AMI không ngăn cập nhật package bên trong hệ điều hành.

Người tái dựng ở region khác cần tra cứu lại AMI và cập nhật đồng bộ region/filter/ID; không dùng một ID bất kỳ để bỏ qua kiểm tra nhà phát hành.

Chạy định dạng và kiểm tra từ thư mục gốc repository:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Kiểm tra data source tiếp tục trả về `ami-0403d346e3210afd6`. Nếu Key Pair vừa khai báo chưa apply, tổng kết vẫn mong đợi `Plan: 1 to add, 0 to change, 0 to destroy.`, resource tạo mới là `aws_key_pair.operator`. Filter AMI không tạo thêm resource AWS; chưa khai báo hoặc apply EC2 trong bước này.

Tham khảo: [Terraform aws_ami — kết hợp filter và chọn một AMI](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/ami).

### 5.21. Khai báo EC2 và các tham chiếu hạ tầng

Đã đối chiếu `data.tf`: bỏ `most_recent`, thêm image-id filter đúng `ami-0403d346e3210afd6` và giữ các filter xác minh image. Bắt đầu khai báo EC2 ở mức các tham chiếu chính; chưa apply cho tới khi hoàn thiện cấu hình đĩa, thiết lập máy chủ, địa chỉ public và kiểm tra trước triển khai.

Giữ resource Key Pair hiện có trong `deploy/terraform/aws/compute.tf`, thêm block bên dưới:

```hcl
resource "aws_instance" "primary" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.medium"
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.primary.id]
  key_name               = aws_key_pair.operator.key_name

  tags = {
    Name    = "mcf-aws-primary"
    Project = "multi-cloud-failover"
  }
}
```

| Thuộc tính | Vai trò |
|---|---|
| `ami` | ID từ data source AMI đã cố định và kiểm tra filter |
| `instance_type` | Loại máy dự kiến `t3.medium`, hai vCPU và 4 GiB RAM |
| `subnet_id` | Đặt EC2 vào subnet public của project, tại AZ `ap-southeast-1c` |
| `vpc_security_group_ids` | Gắn danh sách Security Group cho network interface của máy chủ |
| `key_name` | Chọn Key Pair đăng ký public key của người quản trị |
| Public IPv4 | Subnet giữ `map_public_ip_on_launch = false`; EIP được quản lý bằng resource riêng, không khai báo `associate_public_ip_address` trên instance |

`vpc_security_group_ids` nhận một tập ID, nên viết trong dấu ngoặc vuông dù hiện chỉ có một nhóm. Tham chiếu `aws_security_group.primary.id` gắn các rule SSH/HTTP/HTTPS/outbound với máy chủ khi tạo. Tên tag `mcf-aws-primary` là tên hiển thị, chưa cấu hình vai trò PostgreSQL primary.

Không cần ghi lại AZ trong EC2 vì đã chỉ định subnet ở `ap-southeast-1c`. Các tham chiếu giúp Terraform suy ra dependencies với data source AMI, subnet, Security Group và Key Pair. Private IPv4 được AWS chọn trong subnet khi tạo nếu chưa chỉ định địa chỉ cụ thể.

Từ thư mục gốc repository, chạy:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Nếu Key Pair vẫn chưa apply và chưa có drift ở các resource đã triển khai, kết quả mong đợi:

```text
# aws_instance.primary will be created
# aws_key_pair.operator will be created
...
Plan: 2 to add, 0 to change, 0 to destroy.
```

Kiểm tra AMI đúng ID đã cố định, instance type `t3.medium`, subnet/SG đúng tài nguyên hiện có và key name `mcf-lab`. Subnet tắt tự cấp public IPv4; không khai báo lại cờ đó trên instance khi quản lý EIP riêng. Nếu plan hiển thị root block device hoặc các mặc định khác, đó chưa phải cấu hình compute hoàn chỉnh để triển khai: các thiết lập được bổ sung từng phần ở bước tiếp theo. Không chạy apply tại bước này.

Tham khảo: [Terraform aws_instance](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/instance), [AWS instance IP addressing](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-instance-addressing.html).

### 5.22. Cấu hình root EBS volume của EC2

Đã đối chiếu code EC2 với các tham chiếu đã chuẩn bị; người quản trị xác nhận plan đúng hai resource mới, gồm Key Pair và EC2. Chưa apply compute.

Trong `deploy/terraform/aws/compute.tf`, thêm block sau bên trong `resource "aws_instance" "primary"`, trước block tags của instance:

```hcl
root_block_device {
  volume_size           = 30
  volume_type           = "gp3"
  encrypted             = true
  delete_on_termination = false

  tags = {
    Name    = "mcf-aws-root"
    Project = "multi-cloud-failover"
  }
}
```

| Thuộc tính | Ý nghĩa |
|---|---|
| `root_block_device` | Cấu hình EBS root volume dùng khởi động Ubuntu |
| `volume_size = 30` | Dung lượng đĩa 30 GiB; độc lập với RAM 4 GiB của instance |
| `volume_type = "gp3"` | General Purpose SSD |
| `encrypted = true` | Mã hóa EBS bằng cơ chế AWS KMS |
| `delete_on_termination = false` | Giữ volume khi EC2 bị terminate |
| Tags trong block này | Gắn nhãn cho volume, với Name `mcf-aws-root` |

Thiết kế lab dùng root EBS cho Ubuntu, container runtime, K3s và đường dẫn dữ liệu của local-path PVC. PostgreSQL được triển khai ở giai đoạn workload; dữ liệu của nó sẽ nằm trên đĩa này. Mã hóa đĩa không thay thế cơ chế xác thực PostgreSQL hoặc SSH.

Chọn giữ volume khi terminate để bảo toàn đĩa phục vụ khôi phục và đối chiếu dữ liệu. Volume được giữ tiếp tục phát sinh phí lưu trữ; khi kết thúc lab cần kiểm tra EBS Volumes theo tag Project/Name và dọn volume đã giữ khi dữ liệu không còn cần. Việc khôi phục hoặc gắn lại đĩa vào máy khác cần quy trình riêng, không tự xảy ra chỉ vì đặt cờ này. Stop/start EC2 giữ EBS; thuộc tính DeleteOnTermination điều khiển hành vi khi terminate.

Từ thư mục gốc repository, chạy:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Plan vẫn mong đợi `2 to add, 0 to change, 0 to destroy` nếu chưa apply Key Pair và EC2. Root volume được khai báo trong resource instance nên không tính thành managed resource Terraform thứ ba. Trong phần `aws_instance.primary`, kiểm tra `root_block_device` có dung lượng 30, loại gp3, encrypted true và delete_on_termination false. Các ID volume chưa biết trước khi tạo là bình thường.

Chưa chạy apply tại bước này; tiếp tục hoàn thiện các thiết lập máy chủ và địa chỉ public trước khi triển khai compute.

Tham khảo: [Terraform root_block_device](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/instance#root_block_device), [giữ EBS khi terminate và chi phí volume giữ lại](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/preserving-volumes-on-termination.html), [EBS encryption](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-encryption.html).

### 5.23. Cấu hình CPU credit mode và IMDSv2

Đã đối chiếu cấu hình root EBS 30 GiB, gp3, mã hóa và giữ đĩa khi terminate; người quản trị xác nhận plan vẫn đúng hai resource mới. Chưa apply compute.

Trong `deploy/terraform/aws/compute.tf`, thêm hai block sau bên trong `resource "aws_instance" "primary"`, cùng cấp với `root_block_device`, trước block tags của instance:

```hcl
credit_specification {
  cpu_credits = "standard"
}

metadata_options {
  http_endpoint = "enabled"
  http_tokens   = "required"
}
```

T3 là dòng burstable: CPU có mức baseline, dùng CPU credits tích lũy để chạy vượt baseline. Chọn `standard` giới hạn burst theo credit hiện có; khi credit giảm cạn, CPU dần hạ về baseline. Điều này tránh cơ chế tính phí surplus CPU credits của Unlimited, nhưng cần ghi nhận credit mode và theo dõi credit balance khi đo hiệu năng sau này. CPU credit là đơn vị sử dụng CPU, độc lập với credit tiền của chương trình tài trợ cloud.

`metadata_options` cấu hình truy cập Instance Metadata Service trên EC2. `http_endpoint = "enabled"` bật dịch vụ, `http_tokens = "required"` yêu cầu IMDSv2: client lấy session token rồi gửi token khi đọc metadata. Metadata có thể gồm instance ID, loại máy và thông tin khác của instance. Đây là thiết lập metadata của EC2, không điều khiển HTTP/HTTPS endpoint ứng dụng hoặc rule port 80/443.

Hai block là thuộc tính của resource EC2, không phải managed resource Terraform riêng. Từ thư mục gốc repository, chạy:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Nếu Key Pair và EC2 chưa apply, tổng kết tiếp tục mong đợi `Plan: 2 to add, 0 to change, 0 to destroy.` Trong `aws_instance.primary`, kiểm tra `credit_specification.cpu_credits` là `standard`, metadata endpoint enabled và HTTP tokens required. Chưa chạy apply; Elastic IP và kiểm tra trước triển khai compute được thực hiện tiếp theo.

Tham khảo: [T3 Standard mode](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-standard-mode.html), [Unlimited mode và surplus credits](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-unlimited-mode.html), [IMDSv2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html), [Terraform aws_instance](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/instance).

### 5.24. Cấp và gắn Elastic IP cho EC2

Trạng thái thực hành: đã đối chiếu code có các resource EIP và association đúng cấu hình bên dưới. Cấu hình compute gồm Key Pair, EC2, EIP và association; chưa apply.

Đã đối chiếu code: EC2 có CPU credit mode `standard`, metadata endpoint `enabled` và HTTP tokens `required`. Bắt đầu khai báo public IPv4 cố định để kết nối tới máy chủ.

Trong `deploy/terraform/aws/compute.tf`, giữ nguyên các resource hiện có và thêm hai block sau ở ngoài resource EC2, sau dấu ngoặc đóng của `aws_instance.primary`:

```hcl
resource "aws_eip" "primary" {
  domain = "vpc"

  tags = {
    Name    = "mcf-aws-public-ip"
    Project = "multi-cloud-failover"
  }
}

resource "aws_eip_association" "primary" {
  allocation_id = aws_eip.primary.id
  instance_id   = aws_instance.primary.id

  depends_on = [aws_internet_gateway.primary]
}
```

`aws_eip.primary` cấp một Elastic IP vào account, trong region của provider khi apply. `domain = "vpc"` chỉ định địa chỉ dùng cho VPC, không phải tên miền web và không tạo bản ghi DNS.

`aws_eip_association.primary` gắn địa chỉ đã cấp với EC2. `allocation_id` nhận ID cấp phát dạng `eipalloc-...`, không phải chuỗi public IP; `instance_id` nhận ID máy chủ. Hai tham chiếu làm association chờ EIP và instance được tạo.

`depends_on` bổ sung dependency tường minh để việc gắn EIP chờ Internet Gateway của VPC. Khác với tham chiếu ID đã tạo dependency ngầm định, dòng này biểu diễn yêu cầu hạ tầng mà API gắn địa chỉ cần nhưng hai trường allocation/instance chưa thể hiện trực tiếp. Không thêm thuộc tính `instance` vào `aws_eip` khi đã quản lý việc gắn bằng association resource riêng này.

Trong subnet, giữ `map_public_ip_on_launch = false`; không khai báo `associate_public_ip_address` trong EC2 khi quản lý EIP bằng association riêng. Cờ ở cấp instance là Optional/Computed trong AWS provider; khi gắn EIP, provider có thể đọc cờ này thành true và gây diff thay thế máy nếu code ép false. Xem cách kiểm tra và khắc phục ở mục 5.29. EIP giữ nguyên khi stop/start miễn vẫn giữ allocation và association tương ứng. `admin_cidr` là IP nguồn của người quản trị, còn EIP là địa chỉ đích của EC2; hai giá trị có vai trò riêng.

Vai trò của public IP trong kiến trúc lab:

- Web: DNS sẽ trả về origin tương ứng; client kết nối HTTPS tới EIP, Traefik trên máy chủ xử lý reverse proxy tới ứng dụng. Route 53 xử lý DNS, không chuyển tiếp request HTTPS.
- Quản trị: SSH tới EIP, với TCP 22 giới hạn theo `admin_cidr`.
- Replication liên cloud: EIP sẽ làm endpoint WireGuard phía AWS; rule UDP peer được bổ sung ở giai đoạn WireGuard và giới hạn theo public IP Azure. PostgreSQL giao tiếp qua địa chỉ tunnel theo thiết kế workload.
- Outbound: EC2 có thể đi Internet qua EIP và IGW để tải package/image khi các quy tắc mạng đáp ứng.

Thiết kế hiện dùng một host cho mỗi cloud và không có AWS ALB đứng trước EC2. Traefik vẫn đảm nhiệm reverse proxy ở trong host/K3s. Mô hình khác là public ALB chuyển tiếp tới EC2 qua private IP, quản trị bằng Session Manager và bố trí đường outbound phù hợp. Session Manager giải quyết truy cập quản trị; chuyển sang SSM không tự cung cấp endpoint web công khai hoặc endpoint UDP cho WireGuard. Nếu bỏ EIP trong kiến trúc hiện tại, cần thiết kế lại các đường truy cập đó; chỉ thêm ALB không thay thế đường UDP của WireGuard.

Tham khảo mô hình thay thế: [Load balancer scheme và private targets](https://docs.aws.amazon.com/elasticloadbalancing/latest/userguide/how-elastic-load-balancing-works.html), [Session Manager không cần mở inbound SSH](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html).

EIP chỉ xuất hiện trên AWS sau khi apply thành công. Địa chỉ public cụ thể trong plan hiện hiển thị `(known after apply)`. EIP được cấp vẫn phát sinh phí khi máy dừng hoặc địa chỉ đang idle; stop máy không giải phóng allocation. Chi phí compute, EBS và public IPv4 được đối chiếu trước khi triển khai compute.

Từ thư mục gốc repository, chạy:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Nếu các resource compute hiện vẫn chưa apply, tổng kết mong đợi:

```text
Plan: 4 to add, 0 to change, 0 to destroy.
```

Bốn resource mới là Key Pair, EC2, EIP và EIP association. Root EBS là nested block của EC2; data source AMI chỉ đọc thông tin. Kiểm tra plan rồi tiếp tục hướng dẫn output và kiểm tra trước triển khai, chưa chạy apply ở bước này.

Tham khảo: [Terraform aws_eip](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/eip), [Terraform aws_eip_association](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/eip_association), [AWS Elastic IP](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html).

### 5.25. Khai báo output cho inventory máy chủ

Từ thư mục gốc repository, tạo file:

```bash
touch deploy/terraform/aws/outputs.tf
```

Ghi vào `deploy/terraform/aws/outputs.tf`:

```hcl
output "aws_instance_id" {
  description = "ID of the AWS primary instance"
  value       = aws_instance.primary.id
}

output "aws_private_ip" {
  description = "Private IPv4 address of the AWS primary instance"
  value       = aws_instance.primary.private_ip
}

output "aws_public_ip" {
  description = "Elastic IPv4 address of the AWS primary instance"
  value       = aws_eip.primary.public_ip
}
```

Root module outputs công bố các giá trị cần đọc sau khi triển khai. `output` đặt tên đầu ra, `description` giải thích ý nghĩa và `value` tham chiếu thuộc tính của resource.

| Output | Dùng để |
|---|---|
| `aws_instance_id` | Nhận diện máy chủ khi kiểm tra trạng thái hoặc thao tác vận hành |
| `aws_private_ip` | Kiểm tra địa chỉ trong subnet của VPC |
| `aws_public_ip` | Lấy Elastic IP để SSH, cấu hình DNS và endpoint peer ở các bước sau |

Lấy public IP từ `aws_eip.primary.public_ip` để biểu thị đúng tài nguyên địa chỉ tĩnh đã khai báo. Output không tạo resource AWS hoặc thay đổi Security Group. Giá trị được lưu trong state khi apply; lệnh `terraform output` đọc state, không tự tạo máy chủ hoặc tra cứu thay thế việc apply.

Chạy định dạng và kiểm tra:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
```

Khi validate thành công:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Nếu compute chưa apply, tổng kết mong đợi tiếp tục `Plan: 4 to add, 0 to change, 0 to destroy.` Plan đồng thời có phần `Changes to Outputs` với ba giá trị `(known after apply)`. Outputs không làm tăng số managed resource cần tạo.

Sau lần apply compute thành công ở bước tương ứng, có thể đọc bằng `terraform -chdir=deploy/terraform/aws output` hoặc lấy riêng public IP với `terraform -chdir=deploy/terraform/aws output -raw aws_public_ip`. Chưa chạy các lệnh đọc output này để nghiệm thu lúc tài nguyên và output chưa được apply.

Bước hiện tại chỉ kiểm tra plan. Chưa apply compute; tiếp theo đối chiếu quota đang dùng và chi phí dự kiến trước khi tạo tài nguyên trả phí.

Tham khảo: [Terraform output values](https://developer.hashicorp.com/terraform/language/values/outputs), [terraform output đọc state](https://developer.hashicorp.com/terraform/cli/commands/output).

### 5.26. Đọc instance hiện có để đối chiếu quota trước khi tạo compute

Đã đọc `outputs.tf`: ba output instance ID, private IP và Elastic IP tham chiếu đúng các resource. Compute vẫn chờ bước kiểm tra trước triển khai.

Quota Standard On-Demand đã đọc là 16 vCPU tại Singapore. Để đối chiếu phần đang dùng, liệt kê instance đang pending hoặc running của account tại region này, không giới hạn theo tag project:

```bash
aws ec2 describe-instances \
  --profile default \
  --region ap-southeast-1 \
  --filters Name=instance-state-name,Values=pending,running \
  --query 'Reservations[].Instances[].{Id:InstanceId,Type:InstanceType,State:State.Name,Lifecycle:InstanceLifecycle,Tenancy:Placement.Tenancy}' \
  --output json \
  --no-cli-pager
```

Không lọc theo tag project vì các instance của project khác cùng account/region cũng có thể dùng chung quota. Trạng thái stopped không nằm trong truy vấn này; cần kiểm tra lại quota khi khởi động thêm các máy khác.

Nếu nhận `[]`, API không trả về instance pending/running trong phạm vi truy vấn tại thời điểm kiểm tra. Nếu có danh sách, đối chiếu instance type và số vCPU mặc định của từng loại, đồng thời phân biệt nhóm quota và hình thức mua. `Lifecycle` có giá trị `spot` thuộc quota Spot riêng; instance thông thường On-Demand thường không có trường này nên query hiển thị `null`. Dedicated Host có quota riêng và được nhận diện thêm qua `Tenancy`.

Một `t3.medium` mới cần hai vCPU. Điều kiện đối chiếu cho quota Standard On-Demand là phần sử dụng trong nhóm tương ứng cộng hai không vượt 16. Đây là kiểm tra trước triển khai tại một thời điểm, không phải cam kết capacity tức thời hoặc thay thế kiểm tra của AWS khi launch. Nếu có instance hiện hữu chưa rõ thuộc quota nào, xác định trước khi cộng; không suy ra usage chỉ từ số lượng máy.

Lệnh chỉ đọc thông tin, không start/stop hoặc tạo EC2. Chưa chạy apply compute ở bước này. Sau khi đối chiếu kết quả, tính chi phí dự kiến của EC2, EBS và public IPv4 trước lần triển khai.

Tham khảo: [AWS CLI describe-instances](https://docs.aws.amazon.com/cli/latest/reference/ec2/describe-instances.html), [EC2 instance type quotas](https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html).

Kết quả truy vấn đã nhận là `[]`: không có instance pending/running được trả về tại `ap-southeast-1` trong account/profile đang dùng. Chưa thấy instance hoạt động cần cộng vào phần usage trong phép đối chiếu này. Với quota Standard On-Demand đã đọc là 16 vCPU và nhu cầu hai vCPU của một `t3.medium`, có thể tiếp tục chuẩn bị triển khai theo các điều kiện đã kiểm tra; AWS vẫn xác nhận quota và capacity thực tế khi launch. Chưa tạo EC2.

### 5.27. Ước tính chi phí AWS và định nghĩa cost proxy

Trước khi apply compute, đối chiếu đơn giá niêm yết của các tài nguyên sẽ tạo. Giá được đọc từ AWS Price List Query API cho Singapore và trang giá public IPv4; đây là số tham khảo trước ưu đãi/credit, không phải số dư hoặc hóa đơn thực tế của account.

| Hạng mục | Điều kiện | Đơn giá USD đã đọc |
|---|---|---|
| EC2 `t3.medium` | Linux, On-Demand, Shared tenancy, Singapore | 0.0528/giờ |
| EBS gp3 storage | Singapore; giữ performance baseline | 0.096/GB-month theo đơn vị API |
| Một public IPv4/EIP | Được cấp và giữ trong account, in-use hoặc idle | 0.005/giờ |

Thông tin giúp tái kiểm tra Price List API:

- Service code `AmazonEC2`, region giá `ap-southeast-1`, location `Asia Pacific (Singapore)`.
- Compute SKU `USWP83ASNCY4BSQF`, usage type `APS1-BoxUsage:t3.medium`; filter instanceType `t3.medium`, operatingSystem `Linux`, tenancy `Shared`, preInstalledSw `NA`, capacitystatus `Used`, operation `RunInstances`.
- Storage SKU `X8SY8CJFS8WV7VQN`, usage type `APS1-EBS:VolumeUsage.gp3`; filter productFamily `Storage`, volumeApiName `gp3`.
- Query API được gọi qua endpoint `us-east-1`; region endpoint của Pricing API khác region tài nguyên đang định giá. Các giá trên được chọn bằng điều kiện Singapore.

Ví dụ dùng tháng 30 ngày, 720 giờ. Giữ EBS 30 GiB và một EIP suốt tháng; chỉ thay đổi thời gian EC2 running:

| Hạng mục | Bật EC2 2 giờ/ngày, 60 giờ/tháng | EC2 chạy liên tục, 720 giờ/tháng |
|---|---:|---:|
| Compute | 3.17 USD | 38.02 USD |
| EBS 30 GiB | 2.88 USD | 2.88 USD |
| EIP giữ cả tháng | 3.60 USD | 3.60 USD |
| Tổng ba hạng mục | **9.65 USD** | **44.50 USD** |

Công thức ước lượng cho trường hợp giữ đĩa và IP một tháng:

```text
AWS_cost_proxy_USD = 0.0528 × EC2_running_hours
                   + 0.096 × 30
                   + 0.005 × 720
```

Stop EC2 sau buổi học giảm thời gian compute running. EBS và EIP được giữ vẫn có phí; chỉ dừng instance không loại bỏ hai phần đó. Vì root volume được cấu hình giữ khi terminate, khi kết thúc lab cần quản lý cả volume còn lại. Ước lượng chưa gồm Azure, Route 53/health checks, traffic liên cloud/Internet, snapshots, thuế hoặc dịch vụ bổ sung; chưa trừ Free Tier, credit hay ưu đãi account. Cấu hình Standard CPU credits không sử dụng surplus CPU credit billing của Unlimited; gp3 hiện chưa khai báo performance vượt baseline.

Trong yêu cầu đo đạc của đồ án, **simple cost proxy** là thước đo đại diện gần đúng cho chi phí, không phải network proxy. Có thể dùng tổng VM-hours hoặc một mô hình USD theo giờ chạy và đơn giá. Đây là phép tính phục vụ so sánh các phương án, với phạm vi và giả định được ghi rõ.

Ví dụ cửa sổ đo một giờ: baseline chỉ một VM chạy tương ứng một VM-hour; hệ hai cloud cùng chạy một giờ tương ứng hai VM-hours. VM-hours chưa phản ánh chênh lệch đơn giá/cấu hình giữa cloud, nên phương án báo cáo phù hợp hơn cho project là dùng giờ chạy thực tế nhân đơn giá của từng cloud rồi cộng phần disk/public IP trong cùng cửa sổ đo. Trong giai đoạn lab có thể stop máy sau buổi học; trong cửa sổ đo warm standby, cả primary và standby cần running để so sánh đúng chế độ vận hành.

Ghi nhận cost proxy bằng cùng phạm vi tài nguyên, thời gian đo, đơn vị và bảng giá cho baseline và hệ multi-cloud. Báo cáo kết quả ước tính riêng với chi phí Billing thực tế nếu thu thập được; chưa coi các ví dụ trên là số đo thực nghiệm đã hoàn thành. Hướng dẫn ghi dữ liệu thí nghiệm được bổ sung khi bắt đầu giai đoạn đo đạc.

Nguồn: [AWS Price List Query API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-price-list-query-api.html), [EC2 On-Demand](https://aws.amazon.com/ec2/pricing/on-demand/), [EBS pricing và performance baseline](https://aws.amazon.com/ebs/pricing/), [public IPv4 pricing](https://aws.amazon.com/vpc/pricing/), [billing theo trạng thái EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html).

### 5.28. Lưu plan và triển khai AWS compute

Đã kiểm tra cấu hình hiện tại: `fmt -check` và `validate` đạt; plan đề xuất đúng bốn thao tác create gồm Key Pair, EC2, Elastic IP và association, không thay đổi hoặc xóa tài nguyên hiện có. Ba output instance ID/private IP/public IP hiển thị `(known after apply)`. Việc kiểm tra này chưa tạo compute.

Trước khi triển khai, sao lưu state hiện có ra ngoài repository. Trong Git Bash tại thư mục gốc project:

```bash
mkdir -p ~/.mcf-state-backups/aws
cp deploy/terraform/aws/terraform.tfstate \
  ~/.mcf-state-backups/aws/before-compute-$(date -u +%Y%m%dT%H%M%SZ).tfstate
```

Đây là bản sao local có timestamp, cần giữ trong vùng lưu trữ được bảo vệ của người quản trị; không đưa vào Git. Nó hỗ trợ bảo quản state, không phải backup dữ liệu PostgreSQL.

Lưu plan mới:

```bash
terraform -chdir=deploy/terraform/aws plan -out=compute.tfplan
```

Đọc lại kết quả, xác nhận:

- `Plan: 4 to add, 0 to change, 0 to destroy.`
- AMI `ami-0403d346e3210afd6`, instance type `t3.medium`, subnet hiện có tại `ap-southeast-1c`.
- Key name `mcf-lab`; đúng Security Group của project.
- Root gp3 30 GiB, encrypted true, delete_on_termination false.
- CPU credits standard, metadata tokens required và subnet tắt tự cấp public IPv4; không ép cờ `associate_public_ip_address` trên instance.
- Có EIP cùng association gắn vào instance và ba outputs dự kiến.

Khi saved plan đúng, người quản trị triển khai:

```bash
terraform -chdir=deploy/terraform/aws apply compute.tfplan
```

Saved plan mode thực hiện kế hoạch đã lưu, không hỏi nhập `yes` lần nữa. Lệnh này tạo tài nguyên thật, bắt đầu phát sinh chi phí EC2/EBS/public IPv4 theo trạng thái tài nguyên; xem ước tính ở mục 5.27. Không dùng `network.tfplan` hoặc `security.tfplan` của những lần triển khai trước.

Kết quả thành công mong đợi:

```text
Apply complete! Resources: 4 added, 0 changed, 0 destroyed.
```

Terraform sẽ hiển thị ba output với giá trị thực. Sau đó chạy plan mới để kiểm tra:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Kết quả mong đợi là `No changes. Your infrastructure matches the configuration.` Có thể đọc lại output từ state bằng `terraform -chdir=deploy/terraform/aws output` sau khi apply thành công.

Nếu apply lỗi giữa chừng, giữ nguyên state và gửi/đọc lỗi để xử lý; tài nguyên đã tạo có thể vẫn tồn tại và phát sinh chi phí. Không xóa state hoặc tạo bản sao tài nguyên bằng tay để bỏ qua lỗi. Sau khi xử lý, lập plan mới theo trạng thái đã ghi nhận, không cố dùng lại saved plan đã thực hiện một phần.

Chưa đánh dấu triển khai compute hoàn thành cho tới khi có kết quả thực tế. Kết nối SSH, status checks và kiểm tra Ubuntu được hướng dẫn sau khi tạo thành công; Ubuntu running chưa phải nghiệm thu K3s, PostgreSQL hoặc ứng dụng cloud.

Tham khảo: [Terraform saved plan apply](https://developer.hashicorp.com/terraform/cli/commands/apply#saved-plan-mode), [Terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan).

Kết quả thực hành đã nhận: apply thành công bốn resource và có đủ ba output. Plan đầu tiên sau apply với cờ public IP cũ đề xuất thay thế EC2 và EIP association. Đã xử lý theo mục 5.29 và xác nhận plan No changes; không thực hiện kế hoạch thay thế đó.

### 5.29. Xử lý replacement diff sau khi gắn EIP

Triệu chứng đã quan sát với AWS provider 6.72.0:

```text
associate_public_ip_address = true -> false # forces replacement
Plan: 2 to add, 0 to change, 2 to destroy.
```

Sau khi EIP được gắn vào network interface, provider đọc trạng thái có public IP thành true. Nếu instance cấu hình `associate_public_ip_address = false`, Terraform đề xuất thay thế instance; EIP association cũng phải thay theo instance ID. Đây không phải yêu cầu đổi AMI, AZ hoặc root volume trong trường hợp đã kiểm tra.

Trong `compute.tf`, xóa duy nhất dòng sau khỏi `aws_instance.primary`:

```hcl
associate_public_ip_address = false
```

Giữ `map_public_ip_on_launch = false` trong subnet và giữ hai resource EIP/association. Như vậy subnet tiếp tục điều khiển mặc định public IP khi launch, EIP association quản lý địa chỉ tĩnh, còn provider đọc thuộc tính public IP của instance. Không sửa state bằng tay hoặc đổi sang một giá trị khác chỉ để ép plan.

Chạy:

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
terraform -chdir=deploy/terraform/aws plan
```

Kết quả mong đợi là `No changes. Your infrastructure matches the configuration.` Khi không còn thay đổi, không cần apply; instance và EIP hiện có được giữ nguyên.

Cách sửa bỏ cờ đã được kiểm tra trên bản sao cấu hình và state trong thư mục tạm, dùng provider đã khóa và chỉ chạy plan đọc AWS. Kết quả là exit code 0, No changes. Không chỉnh file Terraform hoặc state gốc trong phép thử; người quản trị thực hiện sửa code rồi kiểm tra lại trên root module chính.

Các dòng `Apply complete! ...` và `No changes. ...` trong tài liệu là kết quả mong đợi, không phải lệnh terminal. Chỉ chạy các dòng lệnh trong block bash.

Đã xác nhận trên cấu hình chính: dòng `associate_public_ip_address` đã được bỏ, subnet vẫn có `map_public_ip_on_launch = false` và người quản trị xác nhận plan báo No changes. Bước kiểm tra sau apply đã đạt; chưa nghiệm thu SSH hoặc workload cloud.

Tham khảo: [provider issue về EIP và replacement diff](https://github.com/hashicorp/terraform-provider-aws/issues/47100), [schema và logic đọc của AWS provider 6.72.0](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/internal/service/ec2/ec2_instance.go), [AWS subnet public IP defaults](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-instance-addressing.html).

### 5.30. Tiếp tục thực hành sau khi dọn hạ tầng

Ở lần tiếp tục thực hành này, `terraform state list` không trả về resource. Truy vấn AWS tại Singapore cũng không tìm thấy EC2 ở trạng thái pending/running/stopping/stopped hoặc EBS volume mang tag `Project=multi-cloud-failover`. Đây là kết quả kiểm tra phạm vi project, không phải kiểm kê mọi dịch vụ trong tài khoản.

Các kết quả apply ở mục trước ghi lại lần triển khai đã thực hiện. Sau khi dọn hạ tầng, cần tạo lại trước khi nghiệm thu SSH; dùng output mới thay cho instance ID/IP của lần trước.

Giữ nguyên các file Terraform, `terraform.tfvars`, lock file, state và SSH key local. Nếu đổi mạng Internet, kiểm tra `admin_cidr` trong `terraform.tfvars` vẫn là public IPv4 hiện tại kèm `/32`, vì Security Group chỉ cho phép SSH từ địa chỉ đó. Không đưa file tfvars hoặc private key lên Git.

Trong Git Bash tại thư mục gốc project, lập kế hoạch mới:

```bash
terraform -chdir=deploy/terraform/aws plan
```

Với cấu hình hiện tại và state trống, kết quả dự kiến:

```text
Plan: 14 to add, 0 to change, 0 to destroy.
```

Mười bốn resource gồm năm resource mạng, Security Group và bốn rule, Key Pair, EC2, Elastic IP và EIP association. AMI data source chỉ tra cứu image, không nằm trong số resource tạo mới.

Đối chiếu region `ap-southeast-1`, AZ `ap-southeast-1c`, instance type `t3.medium`, root gp3 30 GiB và ba output sẽ được xác định sau apply. Lệnh plan chưa tạo máy hoặc bắt đầu phí chạy EC2. Không dùng lại các saved plan của lần triển khai cũ.

Kết quả thực hành đã nhận: người quản trị xác nhận plan đúng `14 to add, 0 to change, 0 to destroy`. Tiếp tục tạo lại hạ tầng từ Git Bash:

```bash
terraform -chdir=deploy/terraform/aws apply
```

Lệnh apply không kèm saved plan sẽ lập kế hoạch mới và yêu cầu xác nhận. Đọc lại đúng 14 resource tạo mới, không change/destroy, đúng account/region và cấu hình đã kiểm tra; sau đó nhập `yes` tại lời nhắc. Đây là bước tạo tài nguyên thật, bắt đầu phát sinh chi phí EC2/EBS/public IPv4 theo trạng thái tài nguyên.

Kết quả mong đợi:

```text
Apply complete! Resources: 14 added, 0 changed, 0 destroyed.
```

Đọc lại ba output mới:

```bash
terraform -chdir=deploy/terraform/aws output
```

Các output `aws_instance_id`, `aws_private_ip`, `aws_public_ip` được dùng cho những bước kiểm tra tiếp theo. Không dùng ID/IP của lần triển khai trước. Nếu apply lỗi giữa chừng, giữ nguyên state để xử lý, không xóa state hoặc dùng lại saved plan cũ. Chưa đánh dấu tạo lại hạ tầng hoặc SSH hoàn thành cho tới khi có kết quả thực tế; status checks và SSH là bước tiếp theo.

Tham khảo: [Terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan), [Terraform apply](https://developer.hashicorp.com/terraform/cli/commands/apply).

### 5.31. Kiểm tra EC2 và kết nối SSH

Người quản trị đã thực hiện apply tạo lại hạ tầng. Đã đọc được ba output mới từ state; truy vấn trực tiếp EC2 xác nhận máy ở trạng thái `running`, system check, instance check và attached EBS check đều `ok`. Kết quả này xác nhận trạng thái hạ tầng; SSH và Ubuntu cần kiểm tra riêng.

Để tự kiểm tra lại từ Git Bash trên laptop:

```bash
instance_id=$(terraform -chdir=deploy/terraform/aws output -raw aws_instance_id)
aws ec2 describe-instance-status \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids "$instance_id" \
  --include-all-instances \
  --query 'InstanceStatuses[].{State:InstanceState.Name,System:SystemStatus.Status,Instance:InstanceStatus.Status,EBS:AttachedEbsStatus.Status}' \
  --output table \
  --no-cli-pager
```

Kết quả mong đợi là `running` và các check `ok`. Nếu mới khởi động còn `initializing`, đợi rồi kiểm tra lại.

Lấy Elastic IP mới và SSH bằng private key local:

```bash
aws_ip=$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)
ssh -i ~/.ssh/mcf-lab "ubuntu@$aws_ip"
```

`-i` chọn private key trên laptop; file `.pub` đã được dùng khi Terraform tạo key pair. `ubuntu` là username của Ubuntu AMI đang dùng. Kết nối đi từ laptop tới Elastic IP qua TCP 22 và chịu giới hạn `admin_cidr` trong Security Group.

Lần đầu SSH hiển thị fingerprint host và hỏi có tin máy chủ hay không. Đối chiếu fingerprint với mục `SSH HOST KEY FINGERPRINTS` trong system log của đúng EC2 (Console: Instances, chọn máy, Actions, Monitor and troubleshoot, Get system log), rồi nhập `yes` khi khớp. Fingerprint host thuộc máy chủ, khác fingerprint public key đăng nhập của người quản trị. Sau khi tạo lại EC2, đọc fingerprint mới; nếu SSH báo host key changed, kiểm tra danh tính máy trước khi xử lý known_hosts.

Khi đăng nhập thành công, terminal đang chạy lệnh trên EC2. Chạy:

```bash
whoami
cat /etc/os-release
```

Kết quả mong đợi: user `ubuntu`, hệ điều hành Ubuntu 24.04 LTS. Nếu key có passphrase, nhập passphrase đã đặt khi tạo key. Nếu timeout, kiểm tra EC2/status checks, public IP và `admin_cidr`; nếu `Permission denied (publickey)`, kiểm tra username và cặp key. Không mở SSH cho toàn Internet để xử lý lỗi kết nối.

Kết quả thực hành đã nhận: người quản trị xác nhận SSH và kiểm tra Ubuntu thành công. Plan sau apply đã được kiểm tra, exit code 0 và thông báo `No changes. Your infrastructure matches the configuration.` Phần hạ tầng AWS đã đạt các bước tạo tài nguyên, status checks, SSH và đối chiếu cấu hình; K3s, WireGuard và ứng dụng được thực hành sau.

Tham khảo: [AWS SSH connection prerequisites](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-to-linux-instance.html), [EC2 status checks](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/monitoring-system-instance-status-check.html).

## 6. Terraform cho hạ tầng Azure

Trong lúc viết và kiểm tra Terraform Azure, chưa cần giữ máy AWS chạy. Hai root module hiện độc lập; hạ tầng AWS chưa có K3s, tool hoặc database cần giữ. Có thể dọn tài nguyên AWS sau khi nghiệm thu SSH rồi tạo lại khi bắt đầu triển khai workload. Cả hai máy cần chạy đồng thời khi kiểm tra WireGuard, streaming replication và diễn tập failover.

Để dọn AWS, trước tiên ghi lại root volume ID của đúng EC2 hiện tại (EC2 Console, chọn instance, tab Storage). Nếu còn ở phiên SSH, dùng `exit` để về laptop, sau đó chạy trong Git Bash tại thư mục gốc repository:

```bash
terraform -chdir=deploy/terraform/aws destroy
```

Đọc kế hoạch chỉ gồm tài nguyên AWS của root này; cấu hình hiện tại dự kiến `0 to add, 0 to change, 14 to destroy`. Nhập `yes` khi đúng phạm vi. Root Azure có state riêng nên không thuộc thao tác destroy này.

Sau `Destroy complete!`, vào EC2 Console tại Singapore, mục Volumes, đối chiếu root volume ID đã ghi, tag `Name=mcf-aws-root`, `Project=multi-cloud-failover`, dung lượng 30 GiB. Khi volume ở trạng thái `available`, xóa volume đó nếu không cần dữ liệu. Cấu hình `delete_on_termination=false` giữ lại EBS sau khi EC2 bị terminate; không bỏ qua bước dọn đĩa. Xóa volume làm mất dữ liệu trên đĩa đó.

Giữ code, tfvars, lock file, state đã được Terraform cập nhật và SSH key trên laptop. Khi cần dùng AWS trở lại, làm plan/apply mới theo mục 5.30, kiểm tra output mới và SSH theo mục 5.31. Không dùng IP, host fingerprint hoặc saved plan của máy đã xóa.

Đã kiểm tra sau khi người quản trị dọn AWS: Terraform state trống; EC2 của lần triển khai mới ở trạng thái `terminated`. Truy vấn tại `ap-southeast-1` không còn instance pending/running/stopping/stopped, EBS volume, Elastic IP, NAT Gateway chưa deleted hoặc snapshot do tài khoản sở hữu. VPC, subnet, Internet Gateway, route table, Security Group mang tag project và key pair `mcf-lab` cũng không còn. Kết quả kiểm tra giới hạn các tài nguyên và region vừa nêu, không phải kiểm toán chi phí toàn tài khoản hoặc các region khác. Có thể tiếp tục cấu hình Azure mà chưa cần tạo lại AWS.

Tham khảo: [EBS được giữ sau termination](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/preserving-volumes-on-termination.html), [xóa EBS volume](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-deleting-volume.html).

### 6.1. Khai báo phiên bản Terraform và AzureRM provider

Giữ hai môi trường trong cùng repository, dùng hai root module `deploy/terraform/aws` và `deploy/terraform/azure`. Mỗi root có state, thư mục `.terraform` và dependency lock file riêng. Các lệnh Azure dưới đây chạy trên laptop trong Git Bash; nếu còn trong SSH vào EC2, chạy `exit` để trở về laptop trước.

Từ thư mục gốc project:

```bash
cd /d/multi-cloud-failover
mkdir -p deploy/terraform/azure
touch deploy/terraform/azure/versions.tf
```

Người thực hành tự điền nội dung sau vào `deploy/terraform/azure/versions.tf`:

```hcl
terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}
```

`required_version` giới hạn phiên bản Terraform CLI, giống root AWS. Provider `hashicorp/azurerm` giúp Terraform gọi Azure Resource Manager API để quản lý Resource Group, VNet, VM và các tài nguyên Azure. Chọn nhánh provider 4.x cho cấu hình của bài thực hành; `~> 4.0` cho phép các phiên bản từ 4.0.0 đến dưới 5.0.0, không có nghĩa phải dùng bản mới nhất trên mọi major version.

Sau khi lưu file, tải provider:

```bash
terraform -chdir=deploy/terraform/azure init
```

Kết quả mong đợi là `Terraform has been successfully initialized!`; Terraform tạo dependency lock file trong root Azure và ghi phiên bản provider thực tế được chọn. Lock file cần được đưa vào Git, còn `.terraform/` và state đã được ignore. Bước này chỉ khởi tạo thư mục làm việc và tải provider, chưa tạo tài nguyên Azure.

Đã nhận xác nhận init thành công và đối chiếu `versions.tf` cùng lock file: AzureRM được khóa ở phiên bản `4.81.0`. Cấu hình provider và lựa chọn subscription được thực hành ở mục 6.2.

Tham khảo: [Terraform provider requirements](https://developer.hashicorp.com/terraform/language/providers/requirements), [AzureRM provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs).

### 6.2. Cấu hình provider và chọn Azure subscription

Trên Git Bash ở thư mục gốc project, tạo file:

```bash
touch deploy/terraform/azure/providers.tf
```

Tự điền vào `deploy/terraform/azure/providers.tf`:

```hcl
provider "azurerm" {
  features {}
}
```

`versions.tf` khai báo provider cần tải; `providers.tf` cấu hình cách sử dụng provider. Khối `features {}` là bắt buộc với AzureRM, để trống nghĩa là dùng các hành vi resource mặc định của provider. AzureRM có thể dùng phiên đăng nhập Azure CLI trên laptop. Trong bài thực hành, subscription được truyền rõ qua biến môi trường `ARM_SUBSCRIPTION_ID`.

Kiểm tra subscription đang được chọn:

```bash
az account show --query '{Name:name,ID:id,State:state}' --output table
```

Kết quả cần là subscription Azure for Students của người thực hành ở trạng thái `Enabled`. Nếu CLI yêu cầu đăng nhập, chạy `az login` và chọn subscription đúng rồi kiểm tra lại. Nếu chọn nhầm subscription, dùng `az account set --subscription '<subscription-id-cua-ban>'` rồi kiểm tra lại trước khi tiếp tục.

Trong cùng terminal, gán subscription cho Terraform:

```bash
export ARM_SUBSCRIPTION_ID="$(az account show --query id --output tsv | tr -d '\r')"
```

`az account show` đọc ID subscription hiện được chọn; `tr -d '\r'` loại ký tự carriage return có thể xuất hiện từ Azure CLI Windows. `export` cho Terraform khởi chạy từ terminal này đọc được biến. Đây là subscription ID, không phải access token. Khi mở terminal Git Bash mới, kiểm tra lại subscription và chạy lại lệnh export trước plan/apply. Nếu lệnh Azure CLI lỗi hoặc không trả ID, xử lý đăng nhập trước khi chạy tiếp.

Kiểm tra định dạng và cấu hình:

```bash
terraform -chdir=deploy/terraform/azure fmt
terraform -chdir=deploy/terraform/azure validate
```

`fmt` thường không in nội dung nếu file đã đúng định dạng. `validate` cần báo `Success! The configuration is valid.` Nó kiểm tra cấu hình, không chứng minh token hay quyền tạo tài nguyên; việc gọi Azure thực tế được kiểm tra khi plan tài nguyên ở bước tiếp theo.

Đã đối chiếu file `providers.tf` do người thực hành tạo; `fmt -check` và `validate` đều đạt. Chưa có khai báo resource trong root Azure ở thời điểm kiểm tra này. Trạng thái CLI đã được đọc là Azure for Students, Enabled, default. Biến môi trường cần được gán trong chính terminal chạy plan/apply như hướng dẫn trên.

Tham khảo: [AzureRM 4.81.0 provider configuration](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/index.html.markdown), [xác thực bằng Azure CLI](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/guides/azure_cli.html.markdown).

### 6.3. Khai báo Resource Group và đọc plan đầu tiên

Resource Group là nhóm quản lý các tài nguyên liên quan của giải pháp Azure. Project sẽ đặt VNet, NSG, public IP, NIC và VM của môi trường standby vào nhóm riêng `mcf-azure-rg` để quản lý vòng đời cùng nhau.

Trên Git Bash ở thư mục gốc project:

```bash
touch deploy/terraform/azure/resource_group.tf
```

Người thực hành tự điền vào `deploy/terraform/azure/resource_group.tf`:

```hcl
resource "azurerm_resource_group" "standby" {
  name     = "mcf-azure-rg"
  location = "southeastasia"

  tags = {
    Project = "multi-cloud-failover"
  }
}
```

`azurerm_resource_group` là loại resource; `standby` là tên tham chiếu trong Terraform; `mcf-azure-rg` là tên trên Azure. `location` của Resource Group xác định nơi lưu metadata của nhóm; resource bên trong có location riêng. Với bài thực hành, các resource có location sẽ được cấu hình ở Southeast Asia theo các bước tiếp theo. Tag giúp nhận diện project, không tự động truyền xuống mọi resource thành viên.

Trong cùng terminal đã chọn đúng subscription và export `ARM_SUBSCRIPTION_ID`, chạy:

```bash
terraform -chdir=deploy/terraform/azure fmt
terraform -chdir=deploy/terraform/azure validate
terraform -chdir=deploy/terraform/azure plan
```

Nếu mở Git Bash mới, thực hiện lại bước kiểm tra subscription và export ở mục 6.2 trước plan. `validate` cần đạt, plan dự kiến có `azurerm_resource_group.standby` với name/location/tag như trên và tổng kết:

```text
Plan: 1 to add, 0 to change, 0 to destroy.
```

Chưa apply ở bước này. Plan lập kế hoạch tạo nhóm, chưa tạo VM hoặc nhóm tài nguyên. Lần đầu provider kết nối subscription có thể cần thêm thời gian kiểm tra/đăng ký các Azure Resource Provider theo cấu hình mặc định. Nếu có lỗi đăng nhập, quyền, policy hoặc provider registration, đọc lỗi để xử lý trước khi đi tiếp; không coi validate thành công là đã nghiệm thu kết nối Azure.

Theo yêu cầu người thực hành, đã chạy `fmt`, `validate` và `plan` trên cấu hình này. `fmt` và `validate` đạt; Azure CLI chọn Azure for Students ở trạng thái Enabled, subscription ID được truyền qua biến môi trường cho tiến trình Terraform. Plan trả đúng `1 to add, 0 to change, 0 to destroy`, gồm `azurerm_resource_group.standby`, tên `mcf-azure-rg`, location `southeastasia`, tag project như trên. Với `-detailed-exitcode`, exit code 2 nghĩa là plan thành công và có thay đổi dự kiến. Chưa chạy apply hoặc tạo Resource Group. Bước tiếp theo sẽ khai báo VNet thuộc nhóm này.

Tham khảo: [Resource Group trong Azure](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/manage-resource-groups-portal), [AzureRM 4.81.0 resource group](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/resource_group.html.markdown).

### 6.4. Khai báo VNet cho Azure standby

VNet là mạng riêng của môi trường Azure, có vai trò tương đương VPC trên AWS. Bài thực hành chọn CIDR `10.30.0.0/16`, tách khỏi dải AWS `10.29.0.0/16` để tránh trùng địa chỉ khi xây dựng kết nối liên cloud.

Tại thư mục gốc repository trong Git Bash, tạo file:

```bash
touch deploy/terraform/azure/network.tf
```

Người thực hành tự nhập vào `deploy/terraform/azure/network.tf`:

```hcl
resource "azurerm_virtual_network" "standby" {
  name                = "mcf-azure-vnet"
  location            = azurerm_resource_group.standby.location
  resource_group_name = azurerm_resource_group.standby.name
  address_space       = ["10.30.0.0/16"]

  tags = {
    Project = "multi-cloud-failover"
  }
}
```

`name` là tên VNet trên Azure; `location` dùng cùng region đã khai báo cho nhóm. `resource_group_name` đặt VNet vào Resource Group của project. Các tham chiếu `azurerm_resource_group.standby.*` giúp Terraform nhận biết dependency để tạo Resource Group trước VNet, không cần khai báo thêm `depends_on`. `address_space` là danh sách CIDR của mạng, tương ứng ý nghĩa dải địa chỉ VPC ở bước AWS.

VNet hiện chưa có subnet. Bước tiếp theo sẽ thêm subnet bằng resource riêng trong cùng file `network.tf`.

Sau khi lưu, trong terminal đã chọn đúng Azure for Students, chạy:

```bash
export ARM_SUBSCRIPTION_ID="$(az account show --query id --output tsv | tr -d '\r')"
terraform -chdir=deploy/terraform/azure fmt
terraform -chdir=deploy/terraform/azure validate
terraform -chdir=deploy/terraform/azure plan
```

Biến môi trường của một tiến trình chạy hộ không được truyền ngược về terminal người thực hành; lệnh export trên giúp terminal hiện tại có subscription ID trước khi plan. Nếu `az account show` lỗi hoặc chọn sai subscription, xử lý theo mục 6.2 trước khi tiếp tục.

Do Resource Group chưa apply ở bước trước, plan dự kiến có hai resource tạo mới là `azurerm_resource_group.standby` và `azurerm_virtual_network.standby`:

```text
Plan: 2 to add, 0 to change, 0 to destroy.
```

Đối chiếu name `mcf-azure-vnet`, address space `10.30.0.0/16`, location `southeastasia` và nhóm `mcf-azure-rg`. Người thực hành đã xác nhận plan chạy đúng; code VNet đã được đọc lại, `fmt -check` và `validate` đạt. Chưa apply ở bước này.

Tham khảo: [AzureRM 4.81.0 virtual network](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/virtual_network.html.markdown).

### 6.5. Khai báo subnet cho VM Azure

Subnet chia không gian địa chỉ của VNet thành một mạng nhỏ hơn để gắn NIC của VM. Với VNet `10.30.0.0/16`, project dùng subnet `10.30.1.0/24`.

Trong file `deploy/terraform/azure/network.tf`, giữ nguyên resource VNet và thêm block sau ở dưới, bên ngoài block VNet:

```hcl
resource "azurerm_subnet" "standby" {
  name                 = "mcf-azure-subnet"
  resource_group_name  = azurerm_resource_group.standby.name
  virtual_network_name = azurerm_virtual_network.standby.name
  address_prefixes     = ["10.30.1.0/24"]

  default_outbound_access_enabled = false
}
```

`virtual_network_name` tham chiếu VNet vừa khai báo; `address_prefixes` là danh sách CIDR của subnet và phải nằm trong không gian địa chỉ VNet. Terraform nhận dependency để tạo Resource Group, VNet rồi subnet theo đúng thứ tự.

`default_outbound_access_enabled = false` tắt cơ chế outbound Internet ngầm của Azure trên subnet. Kiến trúc project sẽ gắn Public IP tĩnh trực tiếp vào NIC của VM ở bước sau để cung cấp kết nối Internet tường minh. Cờ này không quyết định cho phép truy cập Internet vào VM; việc đó còn phụ thuộc Public IP và NSG. Trong giai đoạn hiện tại chưa có VM cần kết nối Internet.

Sau khi lưu, trong Git Bash đã chọn đúng subscription và export `ARM_SUBSCRIPTION_ID`, chạy:

```bash
terraform -chdir=deploy/terraform/azure fmt
terraform -chdir=deploy/terraform/azure validate
terraform -chdir=deploy/terraform/azure plan
```

Nếu mở terminal mới, kiểm tra subscription và export lại theo mục 6.2 trước plan. Do chưa apply các resource trước, plan dự kiến:

```text
Plan: 3 to add, 0 to change, 0 to destroy.
```

Ba resource gồm Resource Group, VNet và subnet. Đối chiếu subnet `mcf-azure-subnet`, CIDR `10.30.1.0/24`, thuộc VNet `mcf-azure-vnet` và cờ default outbound false. Người thực hành đã xác nhận chạy đúng; đã đọc lại code subnet và kiểm tra fmt/validate đạt. Chưa apply.

Tham khảo: [AzureRM 4.81.0 subnet](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/subnet.html.markdown), [Azure default và explicit outbound access](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/default-outbound-access).

### 6.6. Khai báo Network Security Group

Network Security Group (NSG) chứa các rule Allow/Deny cho traffic vào/ra. Có thể liên hệ vai trò kiểm soát truy cập của NSG với Security Group trên AWS; NSG có thêm cơ chế priority để xác định thứ tự xử lý rule. Các rule cho SSH và web được khai báo ở bước tiếp theo.

Trong Git Bash tại thư mục gốc repository, tạo file:

```bash
touch deploy/terraform/azure/security.tf
```

Người thực hành tự điền vào `deploy/terraform/azure/security.tf`:

```hcl
resource "azurerm_network_security_group" "standby" {
  name                = "mcf-azure-nsg"
  location            = azurerm_resource_group.standby.location
  resource_group_name = azurerm_resource_group.standby.name

  tags = {
    Project = "multi-cloud-failover"
  }
}
```

NSG dùng cùng region và Resource Group với mạng của project. Bước này mới khai báo nhóm, chưa có rule tùy chỉnh. Azure có các default rule trong NSG; trong số đó có cho phép traffic VirtualNetwork, cho phép outbound Internet và rule deny cuối cùng. Cho phép outbound ở lớp lọc NSG không thay thế cấu hình đường ra Internet; subnet vẫn tắt default outbound và VM sẽ dùng Public IP gắn NIC ở bước sau.

NSG áp dụng cho tài nguyên sau khi được associate với subnet hoặc NIC. Thiết kế hiện tại sẽ associate NSG với NIC của VM; NIC và association được khai báo ở bước tiếp theo của lớp compute/network interface. Chỉ tạo NSG không tự động gắn nó vào VNet hoặc VM.

Sau khi lưu, trong Git Bash đã chọn subscription và export theo mục 6.2, chạy:

```bash
terraform -chdir=deploy/terraform/azure fmt
terraform -chdir=deploy/terraform/azure validate
terraform -chdir=deploy/terraform/azure plan
```

Vì các resource trước chưa apply, kết quả dự kiến:

```text
Plan: 4 to add, 0 to change, 0 to destroy.
```

Gồm Resource Group, VNet, subnet và NSG. Đối chiếu tên `mcf-azure-nsg`, region `southeastasia`, nhóm `mcf-azure-rg` và tag project. Người thực hành xác nhận plan đúng; code NSG đã được đọc lại và fmt/validate đạt. Chưa apply.

Tham khảo: [AzureRM 4.81.0 network security group](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/network_security_group.html.markdown), [Azure NSG và default rules](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview).

### 6.7. Giới hạn SSH từ public IPv4 của người quản trị

Rule SSH cho phép TCP 22 từ public IPv4 hiện tại của laptop. Root Azure cần khai báo biến và giá trị riêng; các file trong root AWS không tự động được đọc khi chạy Terraform tại `deploy/terraform/azure`.

Trong Git Bash tại thư mục gốc project, tạo hai file:

```bash
touch deploy/terraform/azure/variables.tf
touch deploy/terraform/azure/terraform.tfvars
```

Tự nhập vào `deploy/terraform/azure/variables.tf`:

```hcl
variable "admin_cidr" {
  description = "Public IPv4 CIDR allowed to SSH to the Azure host"
  type        = string
}
```

Xem public IPv4 của kết nối Internet laptop:

```bash
curl -4 -fsS https://checkip.amazonaws.com
```

Điền IP thực tế kèm `/32` vào `deploy/terraform/azure/terraform.tfvars`. Dòng dưới chỉ minh họa cấu trúc, phải thay IP mẫu bằng kết quả thực tế:

```hcl
admin_cidr = "203.0.113.10/32"
```

Địa chỉ `203.0.113.10` là IP tài liệu, không dùng để SSH thật. `/32` giới hạn một IPv4 nguồn. Nếu public IPv4 của laptop thay đổi, cập nhật giá trị trước khi tạo/cập nhật rule. Nếu cùng kết nối Internet với lần làm AWS, hai root có thể dùng cùng giá trị nhưng vẫn cần file tfvars riêng.

Trong `deploy/terraform/azure/security.tf`, giữ NSG và thêm block ở bên ngoài resource NSG:

```hcl
resource "azurerm_network_security_rule" "ssh" {
  name                        = "ssh-from-operator"
  priority                    = 300
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = var.admin_cidr
  destination_address_prefix  = "*"
  resource_group_name         = azurerm_resource_group.standby.name
  network_security_group_name = azurerm_network_security_group.standby.name
}
```

`source_address_prefix` giới hạn IP nguồn; `destination_port_range` là cổng SSH trên VM. `source_port_range="*"` cho phép cổng tạm mà SSH client chọn, không phải mở mọi cổng đích. Destination `*` là mọi địa chỉ đích trong phạm vi NSG được gắn; không thay thế giới hạn source `/32`. NSG sẽ được gắn vào NIC của VM ở bước sau.

`priority=300` là thứ tự xử lý rule; số nhỏ được xét trước số lớn. Các rule tùy chỉnh cùng chiều cần priority riêng; HTTP/HTTPS sẽ dùng các giá trị khác. Tiếp tục dùng resource rule riêng, không trộn thêm block `security_rule` inline vào NSG.

Kiểm tra ignore và cấu hình, trong terminal đã chọn subscription và export theo mục 6.2:

```bash
git check-ignore deploy/terraform/azure/terraform.tfvars
terraform -chdir=deploy/terraform/azure fmt
terraform -chdir=deploy/terraform/azure validate
terraform -chdir=deploy/terraform/azure plan
```

Lệnh check-ignore cần in đường dẫn tfvars; file này được bỏ qua bởi quy tắc `*.tfvars` hiện có. Các file variables và security cần được đưa vào Git khi commit, tfvars được giữ local.

Plan dự kiến:

```text
Plan: 5 to add, 0 to change, 0 to destroy.
```

Gồm bốn resource ở bước trước và `azurerm_network_security_rule.ssh`. Đọc lại source là IPv4 thực tế `/32`, TCP destination 22 và đúng NSG. Người thực hành đã xác nhận plan đúng; đã đối chiếu code variables/rule SSH, fmt/validate đạt và Git check-ignore xác nhận tfvars được bỏ qua. Chưa apply.

Tham khảo: [AzureRM 4.81.0 network security rule](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/network_security_rule.html.markdown).

### 6.8. Cho phép HTTP và HTTPS vào web

Thêm hai rule riêng cho TCP 80 và TCP 443. Web phục vụ người dùng Internet, nên source của hai rule là `Internet`; rule SSH ở mục trước tiếp tục dùng `var.admin_cidr`.

Trong `deploy/terraform/azure/security.tf`, giữ nguyên NSG/rule SSH và thêm hai resource dưới đây ở bên ngoài các block đã có:

```hcl
resource "azurerm_network_security_rule" "http" {
  name                        = "http-from-internet"
  priority                    = 310
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "80"
  source_address_prefix       = "Internet"
  destination_address_prefix  = "*"
  resource_group_name         = azurerm_resource_group.standby.name
  network_security_group_name = azurerm_network_security_group.standby.name
}

resource "azurerm_network_security_rule" "https" {
  name                        = "https-from-internet"
  priority                    = 320
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "Internet"
  destination_address_prefix  = "*"
  resource_group_name         = azurerm_resource_group.standby.name
  network_security_group_name = azurerm_network_security_group.standby.name
}
```

`Internet` là Azure service tag mô tả không gian địa chỉ Internet. Ba inbound rule hiện có priority khác nhau: SSH 300, HTTP 310, HTTPS 320. Rule khác cổng đích nên cho phép từng loại kết nối phù hợp. Mở TCP 443 tại NSG là cấu hình lớp mạng; chứng chỉ TLS và HTTPS Ingress sẽ được cấu hình ở giai đoạn tương ứng.

Trong Git Bash đã chọn subscription và export theo mục 6.2, chạy:

```bash
terraform -chdir=deploy/terraform/azure fmt
terraform -chdir=deploy/terraform/azure validate
terraform -chdir=deploy/terraform/azure plan
```

Kết quả dự kiến:

```text
Plan: 7 to add, 0 to change, 0 to destroy.
```

Gồm Resource Group, VNet, subnet, NSG và ba inbound rule (SSH/HTTP/HTTPS). Kiểm tra SSH vẫn dùng source IPv4 quản trị `/32`, chỉ hai rule web dùng source `Internet`. Không thêm rule public cho PostgreSQL 5432 hoặc Kubernetes API 6443. Người thực hành đã xác nhận plan đúng; đã đọc lại hai rule HTTP/HTTPS và kiểm tra fmt/validate đạt. Chưa apply.

Tham khảo: [AzureRM 4.81.0 network security rule](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/network_security_rule.html.markdown).

### 6.9. Khai báo Public IP tĩnh

Azure Public IP là tài nguyên riêng, sẽ được gắn vào NIC của VM ở bước sau. Vai trò trong kiến trúc tương đương Elastic IP phía AWS: địa chỉ ổn định cho SSH, web, bản ghi DNS origin và endpoint WireGuard. IP thực tế được Azure cấp khi tạo resource; xóa rồi tạo lại không bảo đảm nhận cùng địa chỉ.

Trong `deploy/terraform/azure/network.tf`, giữ VNet/subnet và thêm block dưới đây ở bên ngoài các resource hiện có:

```hcl
resource "azurerm_public_ip" "standby" {
  name                = "mcf-azure-public-ip"
  location            = azurerm_resource_group.standby.location
  resource_group_name = azurerm_resource_group.standby.name
  allocation_method   = "Static"
  sku                 = "Standard"
  ip_version          = "IPv4"
  zones               = ["1", "2", "3"]

  tags = {
    Project = "multi-cloud-failover"
  }
}
```

`allocation_method="Static"` giữ địa chỉ trong vòng đời Public IP resource. `sku="Standard"` dùng Standard public IP với phương thức cấp Static. `zones=["1","2","3"]` khai báo Public IP zone-redundant ở Southeast Asia, hỗ trợ một VM được đặt trong một zone ở bước sau. Đây là cấu hình dự phòng zone của IP, không tạo ba VM hoặc làm cluster một node trở thành HA. Các restriction Zone 2 đã đọc trước đó thuộc hai VM SKU ứng viên, không phải quyết định chọn zone cho VM qua resource Public IP này.

Trong Git Bash đã chọn subscription và export theo mục 6.2, chạy:

```bash
terraform -chdir=deploy/terraform/azure fmt
terraform -chdir=deploy/terraform/azure validate
terraform -chdir=deploy/terraform/azure plan
```

Kết quả dự kiến:

```text
Plan: 8 to add, 0 to change, 0 to destroy.
```

Gồm bảy resource trước và `azurerm_public_ip.standby`. IP thực tế hiển thị `(known after apply)`. Chưa apply hoặc tạo Public IP; bước tiếp theo khai báo NIC để nối subnet, Public IP và VM.

Public IPv4 tĩnh là tài nguyên có tính phí sau khi được cấp theo chính sách billing Azure, kể cả khi VM bị stop/deallocate hoặc IP chưa gắn vào VM. Để tiết kiệm, tiếp tục hoàn thiện code và đọc plan trước khi tạo tài nguyên cần dùng cho buổi thực hành.

Đã đọc lại block Public IP do người thực hành tạo và chuyển sang `network.tf`; `fmt -check` và `validate` đạt. Terraform gộp các file `.tf` trong cùng root module, nên đặt block trong file khác cùng thư mục vẫn có hiệu lực; việc phân file giúp quản lý code. Chỉ giữ một khai báo cho resource này. Chưa apply; kết quả plan của bước NIC tiếp theo sẽ kiểm tra cả Public IP.

Tham khảo: [AzureRM 4.81.0 public IP](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/public_ip.html.markdown), [Azure Public IP và availability zones](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/public-ip-addresses), [Azure IP pricing và billing FAQ](https://azure.microsoft.com/en-us/pricing/details/ip-addresses/).

### 6.10. Tạo NIC và liên kết NSG

NIC là card mạng của VM, có vai trò tương tự ENI trên AWS. NIC tham chiếu subnet để nhận private IPv4, đồng thời tham chiếu Public IP tĩnh đã khai báo để kết nối Internet. Một resource association riêng gắn NSG vào NIC, đưa các rule SSH/HTTP/HTTPS vào phạm vi áp dụng của card mạng đó.

Trong `deploy/terraform/azure/network.tf`, giữ nguyên VNet, subnet, Public IP và thêm hai block dưới đây ở bên ngoài các resource hiện có:

```hcl
resource "azurerm_network_interface" "standby" {
  name                = "mcf-azure-nic"
  location            = azurerm_resource_group.standby.location
  resource_group_name = azurerm_resource_group.standby.name

  ip_configuration {
    name                          = "primary"
    primary                       = true
    subnet_id                     = azurerm_subnet.standby.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.standby.id
  }

  tags = {
    Project = "multi-cloud-failover"
  }
}

resource "azurerm_network_interface_security_group_association" "standby" {
  network_interface_id      = azurerm_network_interface.standby.id
  network_security_group_id = azurerm_network_security_group.standby.id
}
```

Trong `ip_configuration`, `subnet_id` chọn mạng con `10.30.1.0/24`; `private_ip_address_allocation="Dynamic"` để Azure tự cấp private IP cho NIC từ mạng con đó. `public_ip_address_id` gắn Public IP Static của mục 6.9 vào cùng cấu hình IP. `primary=true` đánh dấu cấu hình IP chính của NIC. Tất cả ID được tham chiếu từ resource Terraform, không điền ID thủ công.

Association tham chiếu cả NIC và NSG. Terraform nhận dependency từ các tham chiếu; VM được khai báo ở bước sau sẽ dùng NIC này và chờ association phù hợp trước khi khởi tạo. Bước hiện tại mới khai báo mạng, chưa có resource VM.

Sau khi lưu, trong Git Bash đã chọn subscription và export theo mục 6.2, chạy:

```bash
terraform -chdir=deploy/terraform/azure fmt
terraform -chdir=deploy/terraform/azure validate
terraform -chdir=deploy/terraform/azure plan
```

Kết quả dự kiến:

```text
Plan: 10 to add, 0 to change, 0 to destroy.
```

Mười resource gồm Resource Group, VNet, subnet, NSG, ba inbound rule, Public IP, NIC và NIC–NSG association. Các private IP/ID thực tế vẫn có thể hiển thị `(known after apply)`. Người thực hành đã xác nhận plan chạy đúng; code NIC/association đã được đọc lại, fmt/validate đạt. Chưa apply.

Tham khảo: [AzureRM 4.81.0 network interface](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/network_interface.html.markdown), [NIC–NSG association](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/network_interface_security_group_association.html.markdown).

### 6.11. Tra cứu image Ubuntu và quota trước khi khai báo VM

AWS dùng AMI ID để chọn image hệ điều hành; Azure Marketplace image có thể được xác định bằng URN gồm bốn thành phần:

```text
Publisher:Offer:SKU:Version
```

Với Ubuntu của project, đã tra cứu `Canonical:ubuntu-24_04-lts:server:latest` tại Southeast Asia và đọc được phiên bản cụ thể `24.04.202610250`. Tiếp tục truy vấn chính phiên bản này để kiểm tra lại:

```bash
az vm image show \
  --location southeastasia \
  --urn Canonical:ubuntu-24_04-lts:server:24.04.202610250 \
  --query '{Version:name,Architecture:architecture,Generation:hyperVGeneration}' \
  --output table
```

Kết quả đã đối chiếu từ Azure: version `24.04.202610250`, architecture `x64`, Hyper-V generation `V2`, hệ điều hành Linux; không có Marketplace plan bổ sung trong metadata trả về. Publisher/offer/SKU được xác nhận từ ID image trả về, không dựa vào các thuộc tính top-level không có trong response.

Khi viết `source_image_reference` cho VM ở bước tiếp theo, dùng:

| Thuộc tính | Giá trị |
|---|---|
| publisher | `Canonical` |
| offer | `ubuntu-24_04-lts` |
| sku | `server` |
| version | `24.04.202610250` |

Version cụ thể giúp tái lập cùng image, tương tự việc đã cố định AMI AWS. Tra cứu `latest` chỉ phục vụ tìm phiên bản ứng viên; thay đổi version trong resource VM cần đọc plan vì có thể dẫn tới thay thế máy. Tra cứu image hiện tại chưa tạo VM hoặc đổi code Terraform.

Quota cũng cần kiểm tra trước khi chọn VM:

```bash
az vm list-usage \
  --location southeastasia \
  --query "[?name.value=='cores' || name.value=='standardBasv2Family'].{Name:name.value,Used:currentValue,Limit:limit}" \
  --output table
```

Kết quả đã đọc: tổng regional vCPU `cores` dùng 0/6, family `standardBasv2Family` dùng 0/10. Nếu chọn máy 2 vCPU thuộc họ Basv2 thì còn đủ quota theo hai giới hạn này. Restriction của đúng SKU/zone và capacity khi cấp máy vẫn phải kiểm tra riêng trước triển khai; quota còn không bảo đảm cấp máy thành công.

Đã đọc lại catalog cho `Standard_B2als_v2` tại Southeast Asia: family `standardBasv2Family`, các zone được hỗ trợ là 1, 2, 3; restriction của subscription chỉ nêu Zone 2 với `NotAvailableForSubscription`. Kết quả không nêu Location restriction. Chọn ứng viên size `Standard_B2als_v2` tại Zone 1 cho bước code VM; catalog và quota không bảo đảm capacity lúc apply.

Để tự đối chiếu kết quả SKU/zone từ laptop:

```bash
az vm list-skus \
  --location southeastasia \
  --resource-type virtualMachines \
  --size Standard_B2als_v2 \
  --all \
  --query "[?name=='Standard_B2als_v2'].{Name:name,Family:family,Zones:locationInfo[?location=='southeastasia'].zones[],Restrictions:restrictions}" \
  --output json
```

Ở bước này chỉ tra cứu image, quota và SKU/zone; resource VM được bổ sung ở bước tiếp theo. Các lệnh trên chạy trên laptop trong Azure CLI đã chọn đúng subscription.

Tham khảo: [Azure CLI VM image show](https://learn.microsoft.com/en-us/cli/azure/vm/image?view=azure-cli-latest#az-vm-image-show), [Azure CLI VM usage và SKU](https://learn.microsoft.com/en-us/cli/azure/vm?view=azure-cli-latest), [AzureRM 4.81.0 Linux VM](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/linux_virtual_machine.html.markdown).

### 6.12. Khai báo Ubuntu VM cho Azure standby

Tạo một resource Linux VM dùng NIC/NSG đã khai báo. Size ứng viên `Standard_B2als_v2`, zone `1`, image Ubuntu 24.04 x64 Gen2 version `24.04.202610250` đã được đối chiếu ở mục 6.11. Public IP zone-redundant không thay đổi việc VM chỉ nằm trong một zone.

Trong Git Bash tại thư mục gốc repository:

```bash
touch deploy/terraform/azure/compute.tf
```

Người thực hành tự nhập vào `deploy/terraform/azure/compute.tf`:

```hcl
resource "azurerm_linux_virtual_machine" "standby" {
  name                            = "mcf-azure-standby"
  location                        = azurerm_resource_group.standby.location
  resource_group_name             = azurerm_resource_group.standby.name
  size                            = "Standard_B2als_v2"
  zone                            = "1"
  admin_username                  = "azureuser"
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.standby.id]

  admin_ssh_key {
    username   = "azureuser"
    public_key = file(pathexpand("~/.ssh/mcf-lab.pub"))
  }

  os_disk {
    name                 = "mcf-azure-osdisk"
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 32
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "24.04.202610250"
  }

  tags = {
    Project = "multi-cloud-failover"
  }

  depends_on = [azurerm_network_interface_security_group_association.standby]
}
```

`size` tương đương lựa chọn instance type trên AWS. `zone` cố định vị trí VM tại Zone 1; Azure subnet là tài nguyên regional, nên chọn zone ở VM. `network_interface_ids` nối VM vào NIC có subnet và Public IP của project. Tham chiếu NIC tạo dependency tự động; `depends_on` bổ sung điều kiện chờ NSG được associate với NIC trước khi tạo VM.

`admin_username` tạo tài khoản `azureuser`. Block `admin_ssh_key` cấu hình public key có sẵn cho đúng username, còn `disable_password_authentication=true` sử dụng SSH key để đăng nhập. `pathexpand` đổi `~` thành thư mục home trên laptop; `file` đọc file public `.pub`. Private key `~/.ssh/mcf-lab` tiếp tục được giữ trên laptop và dùng khi SSH sau apply. Provider 4.81.0 hỗ trợ định dạng ssh-ed25519 của cặp key hiện tại.

`os_disk` cấu hình ổ hệ điều hành Standard SSD LRS 32 GiB với caching ReadWrite. Đây là managed OS disk bền vững, chứa Ubuntu và các tool sẽ cài sau. Với `features {}` mặc định hiện có, AzureRM xóa OS disk khi destroy resource VM; cần nhớ hành vi này khi đã có database/data trên cloud. Việc deallocate VM giữ OS disk và dữ liệu. Bước triển khai workload và phương án bảo quản/backup dữ liệu được hướng dẫn ở giai đoạn tương ứng.

`source_image_reference` điền bốn thành phần URN đã tra cứu. Resource VM hiện chỉ tạo máy Ubuntu và cấu hình SSH; K3s, WireGuard, PostgreSQL và web được triển khai sau theo từng lớp.

Sau khi lưu, trong Git Bash đã chọn đúng subscription và export theo mục 6.2:

```bash
terraform -chdir=deploy/terraform/azure fmt
terraform -chdir=deploy/terraform/azure validate
terraform -chdir=deploy/terraform/azure plan
```

Kết quả dự kiến:

```text
Plan: 11 to add, 0 to change, 0 to destroy.
```

So với mục 6.10, chỉ thêm resource `azurerm_linux_virtual_machine.standby`. OS disk là phần được quản lý bên trong resource VM này, không xuất hiện như một `azurerm_managed_disk` riêng trong số đếm. Đối chiếu tên máy, size/zone, image version, public key, NIC và cấu hình disk trong plan. Người thực hành đã xác nhận plan đúng; code VM đã được đọc lại, fmt/validate đạt. Chưa apply hoặc ghi nhận SSH thành công; bước tiếp theo thêm outputs trước khi lập kế hoạch triển khai.

Tham khảo: [AzureRM 4.81.0 Linux VM](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/linux_virtual_machine.html.markdown), [OS disk deletion behavior](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/guides/features-block.html.markdown).

### 6.13. Khai báo outputs cho môi trường Azure

Outputs giúp lấy lại ID máy và các địa chỉ IP từ state sau apply, tương tự ba output đã tạo cho AWS. Khai báo output không tạo thêm tài nguyên cloud.

Trong Git Bash tại thư mục gốc project:

```bash
touch deploy/terraform/azure/outputs.tf
```

Người thực hành tự nhập vào `deploy/terraform/azure/outputs.tf`:

```hcl
output "azure_vm_id" {
  description = "Azure resource ID of the standby VM"
  value       = azurerm_linux_virtual_machine.standby.id
}

output "azure_private_ip" {
  description = "Private IPv4 address of the Azure standby NIC"
  value       = azurerm_network_interface.standby.private_ip_address
}

output "azure_public_ip" {
  description = "Static public IPv4 address of the Azure standby host"
  value       = azurerm_public_ip.standby.ip_address
}
```

`azure_vm_id` là ARM resource ID dạng `/subscriptions/.../resourceGroups/.../providers/Microsoft.Compute/virtualMachines/...`, không phải UUID thuộc tính `virtual_machine_id` của VM. `azure_private_ip` lấy private IPv4 từ NIC; `azure_public_ip` lấy địa chỉ từ Public IP resource. Các tên output là giao diện để dùng lại trong lệnh CLI và bước vận hành sau.

Sau khi lưu, trong Git Bash đã chọn subscription và export theo mục 6.2:

```bash
terraform -chdir=deploy/terraform/azure fmt
terraform -chdir=deploy/terraform/azure validate
terraform -chdir=deploy/terraform/azure plan
```

Số resource dự kiến vẫn giữ nguyên:

```text
Plan: 11 to add, 0 to change, 0 to destroy.

Changes to Outputs:
  + azure_private_ip = (known after apply)
  + azure_public_ip  = (known after apply)
  + azure_vm_id      = (known after apply)
```

Các giá trị thực chỉ được ghi vào state sau apply thành công; lúc đó dùng `terraform -chdir=deploy/terraform/azure output` để đọc lại. Người thực hành đã xác nhận plan đúng mười một resource và ba output; đã đọc lại file outputs, fmt/validate đạt. Chưa chạy apply trong bước outputs. Bước tiếp theo sẽ lưu kế hoạch mới và triển khai sau khi đối chiếu phạm vi tài nguyên và chi phí.

Tham khảo: [Terraform outputs](https://developer.hashicorp.com/terraform/language/values/outputs), [AzureRM Linux VM attributes](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/linux_virtual_machine.html.markdown).

### 6.14. Lưu plan và triển khai hạ tầng Azure

Đã kiểm tra trước triển khai: code VM/outputs đúng các tham chiếu, fmt/validate đạt, admin CIDR là public IPv4 `/32` hợp lệ và tfvars/plan được Git ignore. Ở thời điểm kiểm tra, chưa có state file Azure và `az group exists --name mcf-azure-rg` trả `false`. Đây là kiểm tra tên nhóm dự kiến trong subscription đang chọn, không phải kiểm kê toàn tài khoản.

Đã đối chiếu giá compute công khai qua Azure Retail Prices API ngày 2026-11-07: `Virtual Machines Basv2 Series`, `B2als v2`, region `southeastasia`, loại `Consumption`, Linux, đơn vị `1 Hour`, retail price `0.0472 USD`. Đây là giá tham khảo riêng compute, chưa gồm Standard SSD, Public IPv4, giao dịch đĩa, traffic hoặc thuế/ưu đãi. Credit và số tiền Billing thực tế phụ thuộc subscription.

Khi apply tạo tài nguyên, VM/managed OS disk/Public IP được tính theo trạng thái và chính sách billing tương ứng. Deallocate VM sẽ dừng phí compute khi máy đã được giải phóng; disk và Static Public IP được giữ vẫn có phí. Việc nghỉ hoặc dọn lab cần quản lý các tài nguyên này theo trạng thái thực tế.

Trên Git Bash ở thư mục gốc project, kiểm tra subscription:

```bash
az account show --query '{Name:name,State:state}' --output table
```

Chọn đúng Azure for Students, trạng thái Enabled. Sau đó, trong cùng terminal:

```bash
export ARM_SUBSCRIPTION_ID="$(az account show --query id --output tsv | tr -d '\r')"
terraform -chdir=deploy/terraform/azure plan -out=azure.tfplan
```

Lệnh này lập kế hoạch mới và lưu tại `deploy/terraform/azure/azure.tfplan`. Đọc lại:

- `Plan: 11 to add, 0 to change, 0 to destroy.`
- Resource Group `mcf-azure-rg`, region `southeastasia`.
- VNet `10.30.0.0/16`, subnet `10.30.1.0/24`, NIC gắn Public IP và NSG.
- SSH TCP 22 từ IP quản trị `/32`; HTTP/HTTPS từ Internet.
- VM `mcf-azure-standby`, size `Standard_B2als_v2`, zone `1`.
- User `azureuser`, public key `mcf-lab.pub`, Ubuntu image version `24.04.202610250`.
- OS disk StandardSSD_LRS 32 GiB, ba output được xác định sau apply.

Khi saved plan đúng, người thực hành chạy:

```bash
terraform -chdir=deploy/terraform/azure apply azure.tfplan
```

Saved plan mode thực hiện kế hoạch đã lưu, không hỏi nhập `yes` lần nữa. Đây là lệnh tạo tài nguyên thật; chưa cấu hình K3s, WireGuard hoặc ứng dụng. Giữ terminal chờ kết quả.

Kết quả mong đợi:

```text
Apply complete! Resources: 11 added, 0 changed, 0 destroyed.
```

Đọc lại output sau khi apply thành công:

```bash
terraform -chdir=deploy/terraform/azure output
```

Nếu apply lỗi giữa chừng, giữ nguyên state, đọc/gửi lỗi để xử lý và lập plan mới sau khi sửa nguyên nhân. Các resource đã tạo trước lỗi có thể vẫn tồn tại và phát sinh phí. Không xóa state hoặc tạo bản sao resource bằng tay. Không dùng lại saved plan đã áp dụng một phần hoặc của lần dọn/tạo hạ tầng cũ.

Người thực hành đã xác nhận apply thành công. Đã đọc được ba output mới từ state; truy vấn trực tiếp VM trả `Provisioning succeeded`, `VM running` và VM Agent `Ready`. Post-apply plan trả exit code 0 và `No changes. Your infrastructure matches the configuration.` Chưa nghiệm thu SSH; thực hiện tiếp mục 6.15.

Tham khảo: [Terraform saved plan apply](https://developer.hashicorp.com/terraform/cli/commands/apply#saved-plan-mode), [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices), [Retail Prices endpoint](https://prices.azure.com/api/retail/prices), [Azure Public IP billing FAQ](https://azure.microsoft.com/en-us/pricing/details/ip-addresses/), [Azure VM CLI deallocate](https://learn.microsoft.com/en-us/cli/azure/vm?view=azure-cli-latest#az-vm-deallocate).

### 6.15. Kiểm tra trạng thái và SSH vào VM Azure

Đã xác nhận VM `mcf-azure-standby` được tạo thành công, đang running và Azure VM Agent ready. Plan sau apply không đề xuất thay đổi. Các kiểm tra này xác nhận hạ tầng/agent; kết nối SSH và hệ điều hành được nghiệm thu riêng bên dưới.

Để tự kiểm tra trạng thái từ Git Bash trên laptop:

```bash
az vm get-instance-view \
  --resource-group mcf-azure-rg \
  --name mcf-azure-standby \
  --query '{Name:name,Statuses:instanceView.statuses[].{Code:code,Status:displayStatus},Agent:instanceView.vmAgent.statuses[].displayStatus}' \
  --output json
```

Đối chiếu các trạng thái `ProvisioningState/succeeded`, `PowerState/running` và agent Ready.

Public key đăng nhập đã được cấu hình bằng block `admin_ssh_key` trong `compute.tf`. Đã đối chiếu metadata VM trên Azure: username `azureuser`, password authentication bị tắt, public key khớp file `~/.ssh/mcf-lab.pub` trên laptop và đường dẫn key được cấu hình là `/home/azureuser/.ssh/authorized_keys`. Đây là kiểm tra cấu hình Azure trả về, chưa phải đọc file trong guest hoặc nghiệm thu SSH.

Cần phân biệt cặp key đăng nhập của người quản trị với host key của VM: public key đăng nhập giúp VM xác thực người quản trị, còn fingerprint host giúp SSH client xác thực danh tính máy chủ. Run Command dưới đây phục vụ việc đọc fingerprint host.

Trước lần SSH đầu tiên, lấy fingerprint host từ đúng VM qua Azure Portal: Virtual machines, chọn `mcf-azure-standby`, mở nhóm **Operations** ở menu bên trái, chọn **Run command**, rồi **RunShellScript**. Cần mở trang chi tiết của VM; có thể gõ `Run command` vào ô tìm kiếm menu của trang VM để lọc mục. Nhập lệnh đọc public host key rồi chạy:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Run Command thực hiện lệnh trên VM qua Azure VM Agent. Lệnh trên đọc fingerprint ED25519 của máy chủ, khác fingerprint của cặp key đăng nhập `mcf-lab`. Giữ kết quả để so sánh với lời nhắc khi SSH. Việc chạy Run Command do người thực hành thực hiện, chưa được đánh dấu đã chạy trong kết quả kiểm tra hạ tầng.

Cũng có thể lấy fingerprint từ Git Bash trên laptop bằng Azure CLI:

```bash
MSYS_NO_PATHCONV=1 az vm run-command invoke \
  --resource-group mcf-azure-rg \
  --name mcf-azure-standby \
  --command-id RunShellScript \
  --scripts 'ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub' \
  --query 'value[].message' \
  --output tsv
```

`MSYS_NO_PATHCONV=1` giữ nguyên đường dẫn Linux trong script khi gọi Azure CLI Windows từ Git Bash. Đây là cách thay thế thao tác Portal, cùng dùng Run Command/VM Agent để thực hiện lệnh đọc fingerprint; có thể mất thêm thời gian khởi chạy handler ở lần đầu.

Trong Git Bash trên laptop tại thư mục gốc project, lấy Public IP từ state và SSH:

```bash
azure_ip=$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)
ssh -i ~/.ssh/mcf-lab "azureuser@$azure_ip"
```

`-i` trỏ đến private key local, `azureuser` là username đã cấu hình trong VM resource. Khi SSH hiển thị ED25519 fingerprint, đối chiếu với kết quả Run Command của đúng VM; nhập `yes` khi khớp. Nếu không khớp hoặc có cảnh báo host key changed, dừng xác minh danh tính máy trước khi xử lý known_hosts. Nếu private key có passphrase, nhập passphrase đã đặt lúc tạo key.

Sau khi đăng nhập, các lệnh tiếp theo chạy trên Azure VM:

```bash
whoami
cat /etc/os-release
```

Kết quả mong đợi: user `azureuser` và Ubuntu 24.04 LTS. Nếu SSH timeout, kiểm tra running state, Public IP và source `/32` của rule SSH có đúng public IPv4 hiện tại của laptop. Nếu `Permission denied (publickey)`, kiểm tra đúng username/private key. Không mở rộng rule SSH cho toàn Internet để bỏ qua lỗi cấu hình.

Người thực hành đã xác nhận SSH thành công và hai lệnh kiểm tra trả kết quả đúng: user `azureuser`, Ubuntu 24.04 LTS. Phần nghiệm thu hạ tầng và truy cập máy chủ của giai đoạn 4 đã đạt độc lập trên AWS và Azure. AWS đã được dọn sau nghiệm thu để tiết kiệm, Azure đã triển khai và nghiệm thu SSH. Cần tạo lại AWS trước các bước yêu cầu hai máy chạy đồng thời. K3s, WireGuard, PostgreSQL và ứng dụng cloud được triển khai ở giai đoạn tiếp theo. Checklist budget vẫn chưa được xác nhận thực hiện.

Tham khảo: [Microsoft: connect to a Linux VM và xác minh fingerprint](https://learn.microsoft.com/en-us/azure/virtual-machines/linux-vm-connect), [Run Command qua Portal và CLI](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/run-command), [Azure VM instance view](https://learn.microsoft.com/en-us/cli/azure/vm?view=azure-cli-latest#az-vm-get-instance-view).

### 6.16. Dọn lab Azure sau buổi thực hành và tạo lại

Ở thời điểm dọn lần này, VM mới được nghiệm thu SSH/Ubuntu, chưa cài K3s hoặc triển khai database/workload cloud. Người quản trị yêu cầu xóa hạ tầng Azure để nghỉ, giữ khả năng tạo lại bằng Terraform. Không áp dụng thao tác xóa bên dưới cho máy đã có dữ liệu cần giữ nếu chưa có phương án backup và khôi phục phù hợp.

Trước khi xóa, đối chiếu `terraform state list` của root Azure và inventory trong Resource Group `mcf-azure-rg`. Sao lưu state local ra ngoài Git:

```bash
mkdir -p ~/.mcf-state-backups/azure
cp deploy/terraform/azure/terraform.tfstate \
  ~/.mcf-state-backups/azure/before-destroy-$(date -u +%Y%m%dT%H%M%SZ).tfstate
```

Trong terminal đã chọn đúng Azure for Students và export theo mục 6.2, lập saved destroy plan:

```bash
terraform -chdir=deploy/terraform/azure plan -destroy -out=pause-destroy.tfplan
```

Đọc kỹ phạm vi; ở cấu hình hiện tại phải chỉ gồm mười một resource đã tạo trong Resource Group của project:

```text
Plan: 0 to add, 0 to change, 11 to destroy.
```

Thực hiện kế hoạch đã xem:

```bash
terraform -chdir=deploy/terraform/azure apply pause-destroy.tfplan
```

Lệnh saved plan apply không hỏi nhập `yes` lại. Với `features {}` hiện có, provider xóa managed OS disk cùng VM. Nếu sau này thay đổi cấu hình giữ đĩa, cần kiểm tra và quản lý đĩa còn lại riêng.

Kết quả thực tế của lần dọn này:

```text
Apply complete! Resources: 0 added, 0 changed, 11 destroyed.
```

Đã kiểm tra sau khi xóa: `az group exists --name mcf-azure-rg` trả `false`, không còn resource thuộc nhóm hoặc mang tag Project của đồ án trong kết quả kiểm tra subscription, không còn OS disk `mcf-azure-osdisk` hoặc Public IP `mcf-azure-public-ip`. Azure state có 0 managed resource. Private/public SSH key trên laptop vẫn tồn tại; code, tfvars, lock file và state đã cập nhật được giữ nguyên. State đã được sao lưu tại thư mục `~/.mcf-state-backups/azure/` trước thao tác xóa.

Khi tiếp tục, dùng code hiện có để lập kế hoạch tạo mới, không dùng lại saved plan cũ:

```bash
export ARM_SUBSCRIPTION_ID="$(az account show --query id --output tsv | tr -d '\r')"
terraform -chdir=deploy/terraform/azure plan -out=azure.tfplan
```

Sau khi kiểm tra đúng subscription, cấu hình và mười một resource tạo mới, apply theo mục 6.14 rồi nghiệm thu theo mục 6.15. Dùng outputs và host fingerprint mới. AWS cũng đã được dọn ở phần trước, nên tạo lại từ root AWS khi cần; không dùng IP hoặc saved plan của máy đã xóa. Việc tạo lại được thực hiện khi quay lại thực hành, chưa tự động triển khai trong bước dọn lab.

Tham khảo: [Terraform destroy plan](https://developer.hashicorp.com/terraform/cli/commands/destroy), [AzureRM OS disk deletion behavior](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/guides/features-block.html.markdown).

## 7. Theo dõi tiến độ

- [x] Xác nhận Terraform, AWS CLI, Azure CLI và SSH chạy được trong Git Bash.
- [x] Đăng nhập Azure CLI và xác nhận Azure for Students ở trạng thái Enabled, được chọn mặc định.
- [x] Kiểm tra quyền tại subscription: xác nhận role Owner qua View my access.
- [x] Đọc quota Southeast Asia: tổng region 0/6; BS 0/4; Bsv2 và Basv2 đều 0/10.
- [x] Đọc SKU restriction: B2ls_v2 và B2als_v2 bị hạn chế tại Zone 2, chưa thấy Location restriction trong kết quả.
- [x] Đối chiếu danh sách zone của hai SKU và giá compute retail; size/zone mới ở mức ứng viên, chưa chốt triển khai.
- [x] Đọc policy assignment: Southeast Asia có trong allowed regions; ghi nhận các assignment MFA và ASC Default.
- [ ] Tạo budget tại subscription và xác nhận thresholds/email cảnh báo.
- [x] Xác thực AWS: người quản trị xác nhận STS trả về đúng danh tính tài khoản dùng triển khai.
- [x] Chuẩn bị SSH key local và kiểm tra fingerprint public key ED25519.
- [x] Chọn region, kiểm tra khả năng cấp máy và chuẩn bị SSH key.
- [x] Tạo cấu hình Terraform/provider và quy ước state/lock file.
- [x] Tạo `deploy/terraform/aws/versions.tf`; đã đọc và đối chiếu nội dung khai báo phiên bản.
- [x] Tạo `deploy/terraform/aws/providers.tf`; đã đọc và đối chiếu region/profile.
- [x] Chạy `terraform init` và `terraform validate` thành công cho root module AWS; AWS provider được khóa ở `6.72.0`.
- [x] Khai báo VPC AWS và kiểm tra plan đầu tiên: `1 to add, 0 to change, 0 to destroy`; chưa apply.
- [x] Khai báo subnet AWS và kiểm tra plan: `2 to add, 0 to change, 0 to destroy`; chưa apply.
- [x] Khai báo Internet Gateway và kiểm tra plan: `3 to add, 0 to change, 0 to destroy`; chưa apply.
- [x] Khai báo route table và liên kết subnet; kiểm tra plan: `5 to add, 0 to change, 0 to destroy`; chưa apply.
- [x] Lưu `network.tfplan` và đọc lại đúng plan lớp mạng trước khi apply.
- [x] Apply lớp mạng AWS: năm resource được tạo, state list đủ năm resource và plan mới báo No changes.
- [x] Khai báo Security Group và outbound rule; kiểm tra plan hai resource mới, chưa apply.
- [x] Khai báo `admin_cidr`, gán IPv4 `/32` trong `terraform.tfvars` local và xác nhận Git ignore.
- [x] Khai báo SSH ingress rule và kiểm tra plan ba resource mới; chưa apply.
- [x] Khai báo HTTP/HTTPS ingress rule và kiểm tra plan năm resource mới; chưa apply.
- [x] Apply Security Group và bốn rule; đã đối chiếu state có tổng cộng mười resource.
- [x] Xác nhận plan mới sau apply lớp truy cập báo No changes.
- [x] Đọc quota Standard On-Demand 16 vCPU và xác nhận offering `t3.medium` tại AZ subnet `ap-southeast-1c`; usage/capacity chưa được nghiệm thu.
- [x] Cố định subnet tại `ap-southeast-1c` trong code và xác nhận plan không thay đổi tài nguyên.
- [x] Khai báo data source và tra cứu thành công AMI Ubuntu Server 24.04 x86-64 của Canonical tại Singapore: `ami-0403d346e3210afd6`.
- [x] Khai báo `aws_key_pair.operator` từ public key local; được đề xuất tạo mới trong plan compute, chưa apply.
- [x] Cố định AMI `ami-0403d346e3210afd6` bằng image-id filter và kiểm tra lại data source.
- [x] Khai báo EC2 với các tham chiếu AMI/subnet/SG/Key Pair và kiểm tra plan hai resource mới; chưa apply.
- [x] Cấu hình root EBS gp3 30 GiB, mã hóa và giữ đĩa khi terminate; kiểm tra plan, chưa apply.
- [x] Khai báo CPU credit mode standard và yêu cầu IMDSv2; đã đối chiếu code, chưa apply.
- [x] Khai báo Elastic IP và association; đã đối chiếu code, chưa apply.
- [x] Khai báo ba output và đối chiếu các tham chiếu trong code.
- [x] Xác nhận plan compute bốn resource mới cùng ba output chưa có giá trị; chưa apply.
- [x] Truy vấn instance pending/running tại Singapore trả `[]`; đối chiếu nhu cầu hai vCPU với quota Standard On-Demand 16 vCPU.
- [x] Đối chiếu giá AWS, lập ví dụ chi phí compute/EBS/EIP và định nghĩa cost proxy; chưa phải số đo Billing hoặc thí nghiệm.
- [x] Apply compute thành công bốn resource mới; có đủ ba output với giá trị thực.
- [x] Bỏ cờ public IP ở cấp instance theo mục 5.29 và xác nhận plan của root module chính báo No changes.
- [x] Sau khi dọn lab, kiểm tra state trống và không còn EC2 chưa terminate/EBS mang tag project tại Singapore.
- [x] Tạo lại hạ tầng AWS theo mục 5.30; output mới và EC2 running đã được đối chiếu.
- [x] Xác nhận system, instance và attached EBS status checks đều ok trên EC2 mới.
- [x] Kiểm tra plan sau lần apply tạo lại hạ tầng báo No changes.
- [x] Nghiệm thu status checks, SSH và Ubuntu trên máy chủ AWS.
- [x] Dọn AWS sau nghiệm thu để chuyển sang Azure; đối chiếu state, EC2, EBS, EIP, snapshot, NAT Gateway và tài nguyên mạng trong phạm vi kiểm tra tại Singapore.
- [x] Tự tạo root Azure, khai báo `versions.tf` và chạy `terraform init`; lock file chọn AzureRM 4.81.0.
- [x] Tạo `providers.tf` và kiểm tra fmt/validate đạt; hướng dẫn chọn subscription qua `ARM_SUBSCRIPTION_ID` tại mục 6.2.
- [x] Khai báo Resource Group và kiểm tra plan đầu tiên đúng một resource tạo mới theo mục 6.3; chưa apply.
- [x] Khai báo VNet Azure và kiểm tra plan hai resource tạo mới theo mục 6.4; chưa apply.
- [x] Khai báo subnet Azure và kiểm tra plan ba resource tạo mới theo mục 6.5; chưa apply.
- [x] Khai báo NSG Azure và kiểm tra plan bốn resource tạo mới theo mục 6.6; chưa apply.
- [x] Khai báo admin CIDR và rule SSH Azure, xác nhận tfvars được ignore và plan năm resource tạo mới theo mục 6.7; chưa apply.
- [x] Khai báo HTTP/HTTPS ingress Azure và kiểm tra plan bảy resource tạo mới theo mục 6.8; chưa apply.
- [x] Khai báo Static Standard Public IPv4 Azure trong `network.tf`, kiểm tra fmt/validate đạt theo mục 6.9; chưa apply.
- [x] Khai báo NIC, NIC–NSG association và kiểm tra plan mười resource tạo mới theo mục 6.10; chưa apply.
- [x] Tra cứu Ubuntu 24.04 x64 Gen2, cố định ứng viên image version và đọc quota regional/Basv2 theo mục 6.11.
- [x] Đọc lại SKU restrictions; chọn ứng viên `Standard_B2als_v2` tại Zone 1, tránh Zone 2 bị hạn chế theo mục 6.11.
- [x] Khai báo VM Azure với image đã cố định, SSH key và OS disk; kiểm tra plan mười một resource tạo mới theo mục 6.12; chưa apply.
- [x] Khai báo ba output Azure và kiểm tra plan theo mục 6.13; chưa apply.
- [x] Lưu plan và apply mười một resource Azure theo mục 6.14, nhận ba output thực tế.
- [x] Xác nhận Azure VM provisioning succeeded, running, agent Ready và post-apply plan No changes.
- [x] Nghiệm thu SSH và Ubuntu trên VM Azure theo mục 6.15.
- [x] Dọn lab Azure theo yêu cầu nghỉ thực hành, sao lưu state và kiểm tra VM/OS disk/Public IP/Resource Group đã được xóa theo mục 6.16.
- [x] Khai báo mạng và quy tắc truy cập của hai môi trường.
- [x] Khai báo compute, địa chỉ IP và đĩa.
- [x] Kiểm tra plan rồi triển khai các lớp hạ tầng độc lập trên AWS và Azure.
- [x] Đối chiếu inventory/state, trạng thái máy và ghi nhận xác nhận SSH từ người thực hành; các bằng chứng được mô tả ở mục tương ứng của tài liệu.

Chỉ đánh dấu hoàn thành theo kết quả thực hành. Các lệnh đăng nhập và đoạn cấu hình Terraform sẽ được bổ sung khi bắt đầu bước tương ứng.
