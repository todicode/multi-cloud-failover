# Giai đoạn 5 — K3s và triển khai workload trên hai cloud

## 1. Mục tiêu và đầu ra

Đưa ứng dụng Issues và PostgreSQL lên hai môi trường đã chuẩn bị bằng Terraform ở [giai đoạn 4](giaidoan4_ha_tang_aws_azure_terraform.md). Giai đoạn này thực hành từng lớp: K3s, kết nối WireGuard, database primary/standby và ứng dụng từ container image đã được CI kiểm chứng.

Workload là ứng dụng hoặc dịch vụ được triển khai để chạy trong cluster. Trong project, FastAPI là workload phục vụ giao diện/API, PostgreSQL là workload lưu trữ dữ liệu. K3s quản lý việc chạy các workload đó trên VM.

| Môi trường | Cluster | Vai trò database sau khi triển khai |
|---|---|---|
| AWS | Một cluster K3s độc lập, một EC2 chạy server | PostgreSQL primary, đọc/ghi |
| Azure | Một cluster K3s độc lập, một VM chạy server | PostgreSQL standby, chỉ đọc |

K3s server một node có thể đảm nhiệm cả control plane và chạy Pod ứng dụng. Mỗi cloud khởi tạo cluster riêng; VM Azure không join vào cluster AWS. PostgreSQL truyền WAL qua WireGuard ở các bước sau.

Quy mô một node mỗi cluster được chọn cho phạm vi multi-cloud disaster recovery của project, với hai VM độc lập trên toàn hệ thống. Từng cluster chưa có HA nội bộ: VM mất thì cluster tại cloud đó ngừng phục vụ, và cơ chế phục hồi phải chuyển sang môi trường còn lại. PDF đề tài không quy định ba node/cluster; yêu cầu bổ sung "multi-node cloud service" được diễn giải ở cấp dịch vụ. Xem [đối chiếu phạm vi node](../PROJECT_REQUIREMENTS.md#51-quy-mô-node-và-phạm-vi-high-availability) và điều chỉnh topology nếu tiêu chí nghiệm thu yêu cầu cụ thể multi-node trong từng Kubernetes cluster.

Tiêu chí nghiệm thu được bổ sung theo bước thực hành:

- Mỗi cluster có một node Ready và các thành phần hệ thống hoạt động.
- Hai máy liên lạc qua đường hầm WireGuard khi triển khai kết nối liên cloud.
- AWS có database primary và Azure có standby nhận/replay WAL.
- Hai cluster chạy cùng image digest của ứng dụng.
- Dữ liệu nghiệp vụ ghi trên AWS đọc được từ Azure; endpoint phản ánh đúng vai trò database.

DNS/HTTPS, diễn tập failover, monitoring và đo đạc được thực hành ở các giai đoạn tương ứng của [roadmap](../ROADMAP.md). Các tiêu chí trên chưa được coi là hoàn thành khi chỉ tạo VM hoặc cài xong K3s.

## 2. Trạng thái bắt đầu và cách thực hành

Giai đoạn 4 đã nghiệm thu triển khai, post-apply plan và SSH độc lập trên cả AWS/Azure. Sau buổi thực hành, hai môi trường được dọn để tiết kiệm; code, state local đã cập nhật và SSH key vẫn được giữ.

Giai đoạn này bắt đầu bằng việc tạo lại riêng AWS và cài K3s trên máy đó. Azure được tạo lại khi tới lượt thực hành tương ứng; hai máy cần chạy đồng thời khi kiểm tra WireGuard và replication.

Các lệnh Terraform/AWS/Azure CLI chạy trong Git Bash trên laptop. Lệnh quản trị Linux và cài K3s chạy trong phiên SSH trên đúng VM. Mỗi bước sẽ chỉ rõ nơi chạy; người thực hành tự nhập code và lệnh. Tài liệu được mở rộng khi bắt đầu bước mới.

Khi tới bước cài, sẽ chọn và cố định cùng một phiên bản K3s cho hai cluster. K3s cung cấp container runtime và công cụ quản trị cần thiết; các lệnh cài đặt, cấu hình node và kiểm tra sẽ được bổ sung sau khi máy AWS sẵn sàng.

## 3. Tạo lại máy AWS để bắt đầu

### 3.1. Kiểm tra cấu hình quản trị

Trong Git Bash trên laptop:

```bash
cd /d/multi-cloud-failover
```

Giữ nguyên cấu hình Terraform đã kiểm chứng trong `deploy/terraform/aws/`. Kiểm tra `admin_cidr` trong `deploy/terraform/aws/terraform.tfvars` còn đúng public IPv4 hiện tại của laptop kèm `/32`. Có thể đọc IP hiện tại bằng:

```bash
curl -4 -fsS https://checkip.amazonaws.com
```

Nếu IP đã đổi, tự cập nhật giá trị local trước plan. SSH key `~/.ssh/mcf-lab` và public key đi cùng vẫn được dùng; không tạo hoặc ghi đè key để thay thế một cặp key đang hợp lệ.

### 3.2. Lập plan mới

```bash
terraform -chdir=deploy/terraform/aws plan -out=stage5-aws.tfplan
```

Khi AWS đã được dọn và cấu hình giữ nguyên, kết quả mong đợi:

```text
Plan: 14 to add, 0 to change, 0 to destroy.
```

Đối chiếu đúng account/profile, region `ap-southeast-1`, AZ `ap-southeast-1c`, EC2 `t3.medium`, AMI Ubuntu đã cố định, root gp3 30 GiB, SSH source `/32` và Elastic IP. File `stage5-aws.tfplan` được Git ignore. Không dùng lại saved plan của các lượt triển khai/dọn trước.

### 3.3. Tạo lại hạ tầng khi plan đúng

```bash
terraform -chdir=deploy/terraform/aws apply stage5-aws.tfplan
```

Saved plan apply thực hiện kế hoạch đã lưu mà không hỏi nhập `yes` lại. Bước này tạo tài nguyên thật, phát sinh phí theo compute, EBS và public IPv4. Xem phạm vi chi phí và cách dọn ở tài liệu giai đoạn 4. Azure chưa cần được tạo ở bước này.

Kết quả mong đợi:

```text
Apply complete! Resources: 14 added, 0 changed, 0 destroyed.
```

Đọc thông tin máy mới:

```bash
terraform -chdir=deploy/terraform/aws output
```

Địa chỉ IP và instance ID có thể khác lượt trước. Giữ nguyên state nếu apply lỗi giữa chừng và đọc lỗi để xử lý; chưa đánh dấu máy sẵn sàng khi chỉ có một phần resource được tạo.

Người thực hành đã tạo lại AWS và cung cấp đủ ba output instance ID, private IP và public IP. Tiếp tục kiểm tra trạng thái máy và SSH theo mục 3.5. Mục 3.4 lưu quy trình dọn lab và kết quả của lượt dọn trước.

### 3.4. Tạm dọn AWS trước khi cài K3s

Nếu cần dọn môi trường lab, đối chiếu inventory/state, ghi lại root volume ID của đúng EC2 và sao lưu state ra ngoài repository theo hướng dẫn giai đoạn 4 trước thao tác xóa. Trong Git Bash tại thư mục gốc project, tạo kế hoạch mới:

```bash
terraform -chdir=deploy/terraform/aws plan -destroy -out=pause-destroy.tfplan
```

Đọc lại chỉ đúng phạm vi AWS của project. Với cấu hình hiện tại, tổng kết dự kiến là `0 to add, 0 to change, 14 to destroy`. Sau khi kế hoạch đúng, thực hiện:

```bash
terraform -chdir=deploy/terraform/aws apply pause-destroy.tfplan
```

Root EBS có `delete_on_termination=false`, nên cần xử lý riêng sau khi EC2 terminate. Trong EC2 Console tại Singapore, đối chiếu đúng volume ID đã ghi, tag Project và Name `mcf-aws-root`, dung lượng 30 GiB. Khi volume đã detached và ở trạng thái available, xóa nếu không cần dữ liệu. Xóa EBS làm mất dữ liệu trên ổ đó; áp dụng cho việc dọn lab theo phạm vi đã xác nhận, không thay thế quy trình backup cho database đã có dữ liệu.

Lượt dọn đã thực hiện theo yêu cầu: state được sao lưu tại `~/.mcf-state-backups/aws/`, saved destroy plan chỉ gồm mười bốn resource đã kiểm tra; apply hoàn tất `0 added, 0 changed, 14 destroyed`. Root EBS được đối chiếu ID/tag, xác nhận available và không có attachment rồi xóa riêng.

Kiểm tra sau dọn tại `ap-southeast-1`: không còn EC2 chưa terminated, EBS, Elastic IP, VPC, subnet, Internet Gateway, route table hoặc Security Group mang tag project; key pair `mcf-lab` trên AWS cũng đã được xóa. State AWS có 0 managed resource. Code, tfvars và cặp SSH key local vẫn được giữ; không nghiệm thu K3s trước khi có bước cài đặt và kiểm tra thực tế.

Khi quay lại, dùng plan tạo mới ở mục 3.2 thay cho các saved plan cũ. Các địa chỉ IP và host fingerprint của máy đã xóa không dùng làm thông tin truy cập cho máy được tạo lại.

### 3.5. Kiểm tra EC2 và truy cập Ubuntu

Chạy trong Git Bash tại thư mục gốc repository. Lấy instance ID và Elastic IP từ state của lượt triển khai hiện tại để dùng cho các lệnh tiếp theo.

```bash
MCF_AWS_INSTANCE_ID="$(terraform -chdir=deploy/terraform/aws output -raw aws_instance_id)"
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"

aws ec2 describe-instance-status \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids "$MCF_AWS_INSTANCE_ID" \
  --query 'InstanceStatuses[].{State:InstanceState.Name,System:SystemStatus.Status,Instance:InstanceStatus.Status}' \
  --output table \
  --no-cli-pager
```

Kết quả mong đợi là State `running`, System `ok` và Instance `ok`. Nếu các check còn `initializing`, chờ khoảng 30 giây rồi chạy lại lệnh kiểm tra. Mảng rỗng cần đối chiếu instance ID, region và trạng thái máy trong EC2 Console.

Khi máy đã qua kiểm tra, kết nối bằng private key trên laptop và username của Ubuntu AMI.

```bash
ssh -i ~/.ssh/mcf-lab "ubuntu@$MCF_AWS_PUBLIC_IP"
```

Lần đầu kết nối, SSH hiển thị host fingerprint. Đối chiếu fingerprint của máy mới trong EC2 Console, Actions → Monitor and troubleshoot → Get system log, phần `SSH HOST KEY FINGERPRINTS`. Khi fingerprint khớp, nhập `yes` để lưu nhận dạng host trên laptop. Host fingerprint thuộc máy EC2, còn `mcf-lab` là key xác thực người dùng.

Trong phiên SSH trên EC2, chạy hai lệnh kiểm tra sau.

```bash
whoami
cat /etc/os-release
```

Kết quả mong đợi là user `ubuntu` và Ubuntu `24.04` LTS. Người thực hành đã xác nhận status checks và kết quả SSH đúng như dự kiến cho lượt triển khai hiện tại.

## 4. Chuẩn bị Ubuntu trên AWS

### 4.1. Hoàn tất khởi tạo hệ điều hành và chuẩn bị công cụ

Chạy các lệnh trong mục này ở phiên SSH trên EC2, với user `ubuntu`.

Đợi cloud-init hoàn tất cấu hình lần khởi động đầu tiên.

```bash
sudo cloud-init status --wait
```

Kết quả mong đợi là `status: done`. Nếu lệnh báo lỗi hoặc degraded, lưu kết quả để kiểm tra trước khi thực hiện các bước tiếp theo. Cloud-init xử lý các tác vụ khởi tạo của cloud image, trong đó có thiết lập tài khoản và SSH key.

Cập nhật danh sách gói và cài công cụ tải nội dung qua HTTPS.

```bash
sudo apt-get update
sudo apt-get install -y curl ca-certificates
```

`apt-get update` tải lại danh mục phiên bản gói từ các repository. `apt-get install` cài hoặc cập nhật hai gói được chỉ định. `curl` tải file bằng URL, còn `ca-certificates` cung cấp bộ chứng chỉ CA phục vụ xác minh HTTPS.

Kiểm tra tài nguyên và trạng thái hệ điều hành trước khi cài K3s.

```bash
nproc
free -h
df -h /
swapon --show
sudo ufw status
```

Với EC2 `t3.medium`, dự kiến `nproc` trả về `2`, tổng RAM xấp xỉ 4 GiB, filesystem gốc có dung lượng khả dụng tương ứng với root volume 30 GiB sau khi trừ phần hệ thống. `swapon --show` dự kiến trả về rỗng trên Ubuntu cloud image mới, còn UFW dự kiến `inactive`. Nếu có swap hoặc UFW active, ghi lại để cấu hình theo kết quả thực tế ở bước tiếp theo.

K3s server yêu cầu tối thiểu 2 CPU và 2 GB RAM cho bản thân K3s cùng các thành phần đi kèm. Ứng dụng và PostgreSQL sử dụng thêm tài nguyên, vì vậy cần theo dõi dung lượng khi triển khai workload. Sau khi người thực hành xác nhận kết quả bước chuẩn bị, bổ sung phiên bản K3s cố định và cấu hình cài đặt cho AWS.

Người thực hành đã xác nhận máy có 2 CPU, RAM 3.7 GiB, RAM available 3.3 GiB và filesystem gốc còn 26 GiB. Swap bằng 0, danh sách swap rỗng và UFW inactive.

### 4.2. Tạo cấu hình K3s trên máy AWS

Chạy trong phiên SSH trên EC2. Tạo thư mục cấu hình hệ thống.

```bash
sudo install -d -m 755 /etc/rancher/k3s
```

Tạo file cấu hình cho node AWS.

```bash
sudo tee /etc/rancher/k3s/config.yaml <<'EOF'
node-name: mcf-aws-primary
write-kubeconfig-mode: "0600"
EOF
```

`install -d` tạo thư mục, còn `-m 755` đặt quyền chủ sở hữu được đọc/ghi/truy cập và các user khác được đọc/truy cập. `sudo tee` ghi file bằng quyền root. Cú pháp `<<'EOF'` truyền nguyên khối nội dung tới dòng kết thúc `EOF` vào lệnh tee, bao gồm các dấu nháy trong YAML.

`node-name` đặt tên node Kubernetes để dễ nhận diện khi chạy `kubectl get nodes`. Từ `primary` trong tên là nhãn nhận diện máy AWS theo kiến trúc project. Vai trò đọc/ghi của PostgreSQL được cấu hình riêng khi triển khai database.

`write-kubeconfig-mode` đặt quyền cho file kubeconfig do K3s sinh ra tại `/etc/rancher/k3s/k3s.yaml`. Kubeconfig chứa địa chỉ API server và thông tin xác thực quản trị cluster. Mode `0600` cho phép chủ sở hữu root đọc/ghi file, vì vậy các bước quản trị tại máy dùng `sudo k3s kubectl ...`.

Kiểm tra nội dung đã ghi.

```bash
sudo cat /etc/rancher/k3s/config.yaml
```

Mong đợi đúng hai dòng YAML ở trên. K3s tự đọc `/etc/rancher/k3s/config.yaml` khi khởi động. Người thực hành đã cung cấp kết quả đọc file khớp với cấu hình này.

### 4.3. Cài K3s server bằng phiên bản cố định

Phiên bản dùng cho bài thực hành là `v1.35.1+k3s1`. Cố định cùng giá trị khi cài AWS và Azure để tái lập môi trường. Bản phát hành này tích hợp Kubernetes `v1.35.1`.

Chạy trong phiên SSH trên EC2, sau khi cloud-init trả về `status: done` và hai gói ở mục 4.1 được cài thành công. Tải script cài đặt chính thức vào home của user Ubuntu.

```bash
curl --fail --show-error --location --retry 3 \
  https://get.k3s.io -o install-k3s.sh
```

`--fail` trả về lỗi khi HTTP thất bại, `--show-error` hiển thị lỗi, `--location` theo chuyển hướng và `--retry 3` thử lại với các lỗi thuộc diện retry của curl. `-o` đặt đường dẫn file tải về. Khi lệnh tải thành công, chạy bộ cài.

```bash
sudo env INSTALL_K3S_VERSION='v1.35.1+k3s1' \
  sh ./install-k3s.sh server
```

`sudo` chạy bộ cài bằng quyền root. `env` truyền biến `INSTALL_K3S_VERSION` vào tiến trình cài đặt để chọn đúng phiên bản. `sh` thực thi script vừa tải, còn đối số `server` chọn vai trò K3s server. Node này chạy control plane và các Pod workload trong cùng một máy.

Bộ cài tải và kiểm tra checksum binary K3s, tạo systemd service `k3s`, cấu hình khởi động cùng hệ điều hành và khởi chạy service. K3s sử dụng file cấu hình đã tạo ở mục 4.2, sinh kubeconfig quản trị và sử dụng containerd đi kèm làm container runtime.

Sau khi bộ cài hoàn tất, kiểm tra service và phiên bản.

```bash
sudo systemctl is-active k3s
sudo k3s --version
```

Mong đợi service trả về `active`, dòng phiên bản bắt đầu bằng `k3s version v1.35.1+k3s1`. Ghi nhận kết quả thực tế trước khi đánh dấu hoàn thành. Nếu service lỗi, lấy log bằng lệnh dưới đây để chẩn đoán.

```bash
sudo journalctl -u k3s -n 80 --no-pager
```

Người thực hành đã xác nhận service `active`, K3s `v1.35.1+k3s1` với commit `50fa2d70` và Go `go1.25.6`.

### 4.4. Kiểm tra node và các thành phần hệ thống

Chạy trong phiên SSH trên EC2. Đợi node báo điều kiện Ready, tối đa 180 giây.

```bash
sudo k3s kubectl wait --for=condition=Ready \
  node/mcf-aws-primary --timeout=180s
```

Kết quả mong đợi là `node/mcf-aws-primary condition met`. Tiếp theo đọc trạng thái node, Pod toàn cluster và StorageClass.

```bash
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl get pods -A
sudo k3s kubectl get storageclass
```

`k3s kubectl` gọi công cụ quản trị Kubernetes đi kèm K3s. `get nodes -o wide` hiện thông tin node mở rộng, gồm private IP và container runtime. `get pods -A` liệt kê Pod trong tất cả namespace, còn `get storageclass` liệt kê các lớp cấp phát storage được đăng ký trong cluster.

Tiêu chí kiểm tra ở lượt này như sau.

- Có một node tên `mcf-aws-primary`, trạng thái `Ready`, phiên bản `v1.35.1+k3s1`. Với lượt triển khai hiện tại, INTERNAL-IP dự kiến là `10.29.1.8`.
- Các Pod hệ thống chạy dài hạn chuyển sang `Running`, với số container Ready bằng tổng số container. Pod của Job cài đặt như `helm-install-traefik` có thể ở trạng thái `Completed` sau khi hoàn thành.
- Có StorageClass `local-path` được đánh dấu default.

Các thành phần thường thấy trong namespace `kube-system` gồm CoreDNS để phân giải tên nội bộ, Traefik để nhận traffic vào ứng dụng, local-path-provisioner để cấp volume trên ổ của node, metrics-server để cung cấp số liệu tài nguyên và các Pod ServiceLB phục vụ Traefik. Việc sử dụng storage với PostgreSQL được kiểm tra khi triển khai database.

Các Pod có thể tạm ở `Pending` hoặc `ContainerCreating` khi tải image và khởi tạo. Chờ khoảng một phút rồi đọc lại danh sách. Nếu Pod vẫn lỗi, ghi lại kết quả để kiểm tra trước khi chuyển bước. Có thể lấy sự kiện gần nhất bằng lệnh sau.

```bash
sudo k3s kubectl get events -A --sort-by=.metadata.creationTimestamp
```

Kết quả nghiệm thu do người thực hành cung cấp ngày 2026-11-11 được ghi nhận dưới đây.

- Node `mcf-aws-primary` Ready, role `control-plane`, private IP `10.29.1.8`, K3s `v1.35.1+k3s1`, containerd `2.1.5-k3s1`.
- CoreDNS, local-path-provisioner, metrics-server và Traefik đều `1/1 Running`. Pod `svclb-traefik` đạt `2/2 Running`.
- Hai Job cài Traefik CRD và Traefik đều `Completed`. Job cài Traefik có 2 lần restart trước khi hoàn tất.
- StorageClass `local-path` là default, reclaim policy `Delete`, binding mode `WaitForFirstConsumer`, volume expansion `false`.

`WaitForFirstConsumer` trì hoãn cấp phát/binding volume đến khi có Pod sử dụng PVC, giúp chọn node phù hợp. Với policy `Delete`, xóa PVC dẫn đến thu hồi PV và storage do provisioner quản lý. Khi triển khai PostgreSQL sẽ cấu hình policy giữ dữ liệu phù hợp với quy trình recovery.

Cluster AWS đã đạt bước nghiệm thu node và các thành phần hệ thống. Bước tiếp theo là tạo lại Azure và cài K3s cùng phiên bản để chuẩn bị kết nối giữa hai môi trường.

## 5. Tạo lại Azure và chuẩn bị cluster thứ hai

### 5.1. Kiểm tra subscription và lập plan mới

Mở một tab Git Bash mới trên laptop. Tab SSH AWS tiếp tục dùng để quản trị máy AWS. Trong tab local, vào repository và kiểm tra subscription Azure đang được chọn.

```bash
cd /d/multi-cloud-failover

az account show \
  --query '{Name:name,State:state,IsDefault:isDefault}' \
  --output table
```

Kết quả cần đúng subscription `Azure for Students`, State `Enabled` và IsDefault `True`. Nếu phiên đăng nhập hết hạn hoặc subscription khác, thực hiện lại bước đăng nhập/chọn subscription trong hướng dẫn giai đoạn 4 trước khi tiếp tục.

Đọc public IPv4 hiện tại của laptop.

```bash
curl -4 -fsS https://checkip.amazonaws.com
```

Đối chiếu `admin_cidr` trong `deploy/terraform/azure/terraform.tfvars` với IP vừa đọc kèm `/32`. AWS và Azure dùng file tfvars riêng, nên cần cập nhật giá trị của Azure khi IP quản trị thay đổi.

Trong cùng tab Git Bash, truyền subscription ID cho Terraform và tạo saved plan mới.

```bash
export ARM_SUBSCRIPTION_ID="$(az account show --query id --output tsv | tr -d '\r')"

terraform -chdir=deploy/terraform/azure plan -out=stage5-azure.tfplan
```

`ARM_SUBSCRIPTION_ID` chỉ định subscription cho AzureRM provider trong terminal hiện tại. `tr -d '\r'` loại bỏ ký tự carriage return có thể xuất hiện khi đọc output CLI Windows qua Git Bash.

State local Azure có 0 managed resource tại thời điểm bắt đầu bước này. Với cấu hình đã kiểm chứng và môi trường Azure đã dọn từ giai đoạn 4, tổng kết dự kiến là `Plan: 11 to add, 0 to change, 0 to destroy.` Đối chiếu plan với các thông số sau.

- Resource Group `mcf-azure-rg`, region `southeastasia`.
- VNet `10.30.0.0/16`, subnet `10.30.1.0/24` và NSG áp dụng cho NIC.
- VM `mcf-azure-standby`, size `Standard_B2als_v2`, Zone `1`, user `azureuser` và public key từ `~/.ssh/mcf-lab.pub`.
- Ubuntu image version `24.04.202610250`, OS disk 32 GiB `StandardSSD_LRS` và Static Standard Public IP.
- Rule SSH chỉ cho public IPv4 quản trị `/32` đã cấu hình.

File saved plan được Git ignore. Đọc và xác nhận plan trước khi thực hiện apply ở bước tiếp theo.

Người thực hành đã xác nhận plan tạo lại Azure khớp với tổng kết và thông số dự kiến ở bước này.

### 5.2. Apply saved plan và đọc outputs Azure

Trong cùng tab Git Bash trên laptop đã chọn đúng subscription và export `ARM_SUBSCRIPTION_ID`, chạy saved plan vừa kiểm tra.

```bash
terraform -chdir=deploy/terraform/azure apply stage5-azure.tfplan
```

Saved plan apply thực hiện ngay kế hoạch đã lưu. Bước này tạo VM, OS disk, Public IP và các tài nguyên mạng thật, phát sinh phí theo tài nguyên Azure được sử dụng. Tổng kết dự kiến là `Apply complete! Resources: 11 added, 0 changed, 0 destroyed.`

Nếu apply báo lỗi, giữ state hiện tại và đọc lỗi trước khi lập kế hoạch tiếp theo. State ghi nhận các resource đã tạo thành công trong quá trình apply.

Sau khi apply thành công, đọc outputs.

```bash
terraform -chdir=deploy/terraform/azure output
```

Ba output cần có gồm `azure_vm_id`, `azure_private_ip` và `azure_public_ip`. `azure_vm_id` là ARM resource ID của VM, `azure_private_ip` thuộc subnet `10.30.1.0/24`, còn `azure_public_ip` là Static Public IP để kết nối SSH. Lượt tạo mới có thể được cấp địa chỉ khác lượt triển khai trước.

Người thực hành đã cung cấp đủ ba output của lượt triển khai mới, với private IP `10.30.1.4`. Bước tiếp theo kiểm tra trạng thái VM và truy cập SSH.

### 5.3. Kiểm tra VM và SSH vào Ubuntu trên Azure

Trong tab Git Bash trên laptop đã chọn đúng subscription, đọc trạng thái máy và các địa chỉ IP.

```bash
az vm show \
  --resource-group mcf-azure-rg \
  --name mcf-azure-standby \
  --show-details \
  --query '{Name:name,Provisioning:provisioningState,Power:powerState,PublicIP:publicIps,PrivateIP:privateIps}' \
  --output table
```

Mong đợi Provisioning `Succeeded`, Power `VM running` và các IP khớp với Terraform outputs của lượt triển khai hiện tại.

Trước lần SSH đầu tiên, mở Azure Portal → Virtual machines → `mcf-azure-standby` → Operations → Run command → RunShellScript. Chạy lệnh đọc fingerprint của SSH host key trên VM.

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Ghi lại giá trị `SHA256:...` để đối chiếu với SSH client. Public key đăng nhập đã được Terraform cấu hình trong resource VM qua `admin_ssh_key`.

Quay lại tab Git Bash trên laptop, lấy Public IP từ Terraform output và SSH vào VM.

```bash
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"
ssh -i ~/.ssh/mcf-lab "azureuser@$MCF_AZURE_PUBLIC_IP"
```

Khi SSH hỏi xác nhận host, đối chiếu fingerprint ED25519 với giá trị vừa đọc qua Azure Portal rồi nhập `yes` khi khớp. Sau khi đăng nhập, chạy các lệnh sau trong phiên SSH Azure.

```bash
whoami
cat /etc/os-release
```

Mong đợi user `azureuser` và Ubuntu `24.04` LTS. Người thực hành đã xác nhận trạng thái máy và kết quả SSH khớp với hướng dẫn cho lượt triển khai hiện tại.

### 5.4. Chuẩn bị Ubuntu trên Azure

Chạy trong phiên SSH Azure với user `azureuser`. Hoàn tất tác vụ khởi tạo máy trước khi cài các gói.

```bash
sudo cloud-init status --wait
```

Mong đợi `status: done`. Nếu có lỗi hoặc degraded, lưu kết quả để kiểm tra trước khi tiếp tục. Khi khởi tạo thành công, cập nhật danh sách gói và chuẩn bị công cụ tải bộ cài K3s qua HTTPS.

```bash
sudo apt-get update
sudo apt-get install -y curl ca-certificates
```

Kiểm tra tài nguyên và trạng thái máy Azure.

```bash
nproc
free -h
df -h /
swapon --show
sudo ufw status
```

VM `Standard_B2als_v2` dự kiến có 2 vCPU và RAM gần 4 GiB theo số liệu hệ điều hành. OS disk được cấu hình 32 GiB, dung lượng filesystem gốc hiển thị có thể thấp hơn do phân vùng và phần hệ thống. Swap dự kiến tắt và UFW inactive trên image mới. Nếu swap đang bật hoặc UFW active, lưu kết quả để điều chỉnh cấu hình ở bước tiếp theo.

Các lệnh có cùng chức năng với mục 4.1 trên AWS. Cần kiểm tra kết quả riêng trên Azure để xác nhận điều kiện của máy thứ hai.

Người thực hành đã cung cấp kết quả máy Azure có 2 CPU, RAM 3.8 GiB, RAM available 3.3 GiB và filesystem gốc còn trống 28 GiB. Swap bằng 0, danh sách swap rỗng và UFW inactive.

### 5.5. Tạo cấu hình K3s trên Azure

Chạy trong phiên SSH Azure với user `azureuser`. Tạo thư mục và file cấu hình K3s.

```bash
sudo install -d -m 755 /etc/rancher/k3s

sudo tee /etc/rancher/k3s/config.yaml <<'EOF'
node-name: mcf-azure-standby
write-kubeconfig-mode: "0600"
EOF
```

`node-name` đặt tên node Azure là `mcf-azure-standby`. Tên này giúp nhận diện môi trường khi quản trị Kubernetes. Vai trò PostgreSQL standby sẽ được thiết lập trong bước triển khai database.

`write-kubeconfig-mode` đặt quyền đọc/ghi kubeconfig cho chủ sở hữu root, giống cấu hình AWS. Các lệnh quản trị cluster tại VM dùng `sudo k3s kubectl ...`.

Kiểm tra file vừa tạo.

```bash
sudo cat /etc/rancher/k3s/config.yaml
```

Mong đợi đúng hai dòng YAML ở trên. Người thực hành đã xác nhận cấu hình Azure khớp với hướng dẫn.

### 5.6. Cài K3s server trên Azure

Chạy trong phiên SSH Azure với user `azureuser`, sau khi cloud-init hoàn tất và các gói ở mục 5.4 được cài thành công. Tải script cài đặt chính thức vào thư mục hiện tại.

```bash
curl --fail --show-error --location --retry 3 \
  https://get.k3s.io -o install-k3s.sh
```

Khi tải thành công, thực hiện cài đặt cùng phiên bản đã dùng trên AWS.

```bash
sudo env INSTALL_K3S_VERSION='v1.35.1+k3s1' \
  sh ./install-k3s.sh server
```

Ý nghĩa các tùy chọn được giải thích ở mục 4.3. Bộ cài tạo service `k3s` và khởi chạy K3s server trên Azure. K3s đọc cấu hình tại `/etc/rancher/k3s/config.yaml`, dùng tên node `mcf-azure-standby` và khởi tạo cluster Azure độc lập.

Sau khi cài hoàn tất, kiểm tra service và phiên bản.

```bash
sudo systemctl is-active k3s
sudo k3s --version
```

Mong đợi `active` và dòng phiên bản bắt đầu bằng `k3s version v1.35.1+k3s1`. Nếu cài đặt hoặc service lỗi, lưu kết quả cùng log gần nhất để kiểm tra.

```bash
sudo journalctl -u k3s -n 80 --no-pager
```

Người thực hành đã xác nhận service và phiên bản K3s trên Azure đúng như hướng dẫn.

### 5.7. Kiểm tra cluster K3s trên Azure

Chạy trong phiên SSH Azure với user `azureuser`. Đợi node Azure đạt điều kiện Ready.

```bash
sudo k3s kubectl wait --for=condition=Ready \
  node/mcf-azure-standby --timeout=180s
```

Mong đợi `node/mcf-azure-standby condition met`. Đọc trạng thái cluster để đối chiếu với kết quả AWS.

```bash
sudo k3s kubectl get nodes -o wide
sudo k3s kubectl get pods -A
sudo k3s kubectl get storageclass
```

Tiêu chí nghiệm thu cluster Azure được liệt kê dưới đây.

- Có một node `mcf-azure-standby`, trạng thái `Ready` và phiên bản `v1.35.1+k3s1`. INTERNAL-IP của lượt triển khai hiện tại dự kiến `10.30.1.4`.
- CoreDNS, Traefik, local-path-provisioner, metrics-server và Pod ServiceLB đạt `Running` với số container Ready đầy đủ.
- Các Job cài Traefik và CRD hoàn tất với trạng thái `Completed`.
- Có StorageClass `local-path` được đánh dấu default.

Lệnh quản trị trong phiên SSH Azure sử dụng kubeconfig local của cluster Azure. Kết quả `get nodes` trên từng máy sẽ có một node thuộc cluster tại máy đó. Cặp cluster này dùng để triển khai hai môi trường độc lập trong kiến trúc multi-cloud.

Nếu Pod còn `Pending` hoặc `ContainerCreating` trong lúc khởi tạo, chờ khoảng một phút rồi đọc lại danh sách. Với lỗi kéo dài, lấy sự kiện để kiểm tra trước khi chuyển bước.

```bash
sudo k3s kubectl get events -A --sort-by=.metadata.creationTimestamp
```

Người thực hành đã xác nhận node Azure Ready, các Pod hệ thống và StorageClass đạt các tiêu chí trên, tương tự kết quả AWS. Hai cluster đã sẵn sàng cho bước kết nối liên cloud.

## 6. Kết nối hai máy bằng WireGuard

### 6.1. Địa chỉ và luồng kết nối

WireGuard tạo đường hầm mạng có mã hóa giữa hai VM qua public IP của mỗi cloud. Trên từng máy sẽ cấu hình interface `wg0` với địa chỉ tunnel do project chọn.

| Máy | Private IP của cloud ở lượt triển khai hiện tại | Địa chỉ tunnel dự kiến |
|---|---|---|
| AWS | `10.29.1.8` | `10.200.29.1/32` |
| Azure | `10.30.1.4` | `10.200.29.2/32` |

Luồng replication PostgreSQL sẽ kết nối qua các địa chỉ tunnel. WireGuard mã hóa packet và vận chuyển qua UDP giữa các public endpoint. Port UDP được chọn cho project là `51820` trên cả hai máy. Private IP cloud do VPC/VNet cấp, còn địa chỉ tunnel được đặt trong cấu hình WireGuard.

Các bước tiếp theo sẽ tạo key riêng trên từng máy, thêm rule UDP 51820 giới hạn source public IP `/32` của peer, cấu hình interface và kiểm tra handshake cùng kết nối hai chiều. Peer AllowedIPs sẽ giới hạn ở địa chỉ tunnel `/32` của máy còn lại. Đối chiếu các route hiện tại trước khi bật tunnel để xác nhận địa chỉ được chọn phù hợp với môi trường thực tế.

### 6.2. Cài công cụ WireGuard trên cả hai máy

Chạy các lệnh sau một lần trong phiên SSH AWS với user `ubuntu`, rồi một lần trong phiên SSH Azure với user `azureuser`.

```bash
sudo apt-get install -y wireguard
wg --version
```

Gói WireGuard trên Ubuntu cung cấp công cụ `wg` và `wg-quick` phục vụ tạo key, cấu hình và quản trị tunnel. Lệnh kiểm tra dự kiến hiển thị dòng bắt đầu bằng `wireguard-tools v`.

Người thực hành đã xác nhận cài công cụ WireGuard trên cả AWS và Azure.

### 6.3. Tạo cặp key riêng trên từng máy

Chạy cùng các lệnh sau trong phiên SSH AWS và phiên SSH Azure. Mỗi lần `wg genkey` tạo một private key ngẫu nhiên riêng cho máy đang chạy lệnh.

```bash
sudo install -d -m 700 /etc/wireguard

sudo sh -c '
set -eu
set -C
umask 077
wg genkey > /etc/wireguard/private.key
wg pubkey < /etc/wireguard/private.key > /etc/wireguard/public.key
'
```

`sudo sh -c` thực thi cả khối shell và phép ghi file bằng quyền root. `set -e` dừng khi lệnh thất bại, `set -u` báo lỗi nếu tham chiếu biến chưa đặt và `set -C` từ chối ghi đè file hiện có bằng phép chuyển hướng `>`. Nếu báo file đã tồn tại, kiểm tra key hiện có và tiếp tục với cặp key hợp lệ đã tạo.

`umask 077` giới hạn quyền các file mới cho chủ sở hữu. Thư mục có mode `700`, private key và public key được tạo với mode `600`, thuộc root. `wg pubkey` đọc private key qua stdin và sinh public key tương ứng.

Đọc public key trên mỗi máy để dùng khi cấu hình peer.

```bash
sudo cat /etc/wireguard/public.key
```

Ghi lại hai giá trị và gắn nhãn rõ ràng `AWS public key` và `Azure public key`. Mỗi giá trị là một chuỗi base64 trên một dòng. Private key giữ trên chính VM đã tạo. Public key AWS được dùng trong cấu hình peer của Azure, và public key Azure được dùng trong cấu hình peer của AWS.

Để kiểm tra quyền file, chạy lệnh sau.

```bash
sudo ls -l /etc/wireguard/private.key /etc/wireguard/public.key
```

Mong đợi hai file thuộc `root` và quyền `-rw-------`. Nếu chỉ có private key sau một lần tạo bị gián đoạn, có thể khôi phục public key tương ứng bằng `wg pubkey` đọc private key hiện có, với cùng quyền root và umask như trên.

Bước tiếp theo thêm rule mạng UDP 51820 giới hạn public IP của peer bằng Terraform, rồi cấu hình WireGuard bằng các key đã chuẩn bị.

### 6.4. Khai báo rule WireGuard phía AWS bằng Terraform

Thực hiện trên laptop trong editor và Git Bash tại thư mục gốc repository. Bước này cho phép Azure gửi packet WireGuard vào EC2 qua UDP 51820.

Thêm biến sau vào `deploy/terraform/aws/variables.tf`.

```hcl
variable "wireguard_peer_cidr" {
  description = "Public IPv4 CIDR of the Azure WireGuard peer"
  type        = string
}
```

Đọc Public IP hiện tại của Azure bằng lệnh sau trong Git Bash.

```bash
terraform -chdir=deploy/terraform/azure output -raw azure_public_ip
```

Trong `deploy/terraform/aws/terraform.tfvars`, giữ giá trị `admin_cidr` và thêm giá trị của biến mới. Thay placeholder bằng Public IP vừa đọc kèm `/32`.

```hcl
wireguard_peer_cidr = "<AZURE_PUBLIC_IPV4>/32"
```

Biến này nhận IP của máy Azure gửi traffic vào AWS. `admin_cidr` tiếp tục nhận IP quản trị laptop cho SSH. Mỗi giá trị được áp dụng cho rule tương ứng.

Thêm resource sau vào `deploy/terraform/aws/security.tf`.

```hcl
resource "aws_vpc_security_group_ingress_rule" "wireguard" {
  security_group_id = aws_security_group.primary.id
  description       = "Allow WireGuard from Azure peer"
  cidr_ipv4         = var.wireguard_peer_cidr
  ip_protocol       = "udp"
  from_port         = 51820
  to_port           = 51820
}
```

`cidr_ipv4` giới hạn địa chỉ nguồn, `ip_protocol` chọn UDP, còn hai trường port bằng nhau giới hạn rule ở đúng port 51820. Public IP peer phải được cập nhật trong tfvars nếu môi trường Azure được tạo lại với địa chỉ khác.

Trong Git Bash trên laptop, format, validate và lập plan mới.

```bash
terraform -chdir=deploy/terraform/aws fmt
terraform -chdir=deploy/terraform/aws validate
terraform -chdir=deploy/terraform/aws plan -out=wireguard-aws.tfplan
```

Với state và hạ tầng AWS hiện tại khớp cấu hình trước bước này, tổng kết dự kiến là `Plan: 1 to add, 0 to change, 0 to destroy.` Resource mới cần đúng `aws_vpc_security_group_ingress_rule.wireguard`, source Azure Public IP `/32`, protocol UDP và port 51820. Đọc lại các thay đổi nếu plan khác dự kiến trước khi chuyển sang apply.

Sau khi thêm rule này, cấu hình AWS có tổng cộng 15 managed resource. Các con số 14 resource ở mục tạo/dọn trước đó ghi nhận cấu hình tại thời điểm thực hành các bước đó. Người thực hành đã xác nhận tổng kết plan đúng như dự kiến.

### 6.5. Apply rule WireGuard phía AWS

Trong tab Git Bash trên laptop tại thư mục gốc repository, chạy saved plan vừa đối chiếu.

```bash
terraform -chdir=deploy/terraform/aws apply wireguard-aws.tfplan
```

Kết quả mong đợi là `Apply complete! Resources: 1 added, 0 changed, 0 destroyed.` Đây là bước tạo rule ingress trong Security Group đang gắn với EC2.

Sau khi apply thành công, đọc thuộc tính resource trong Terraform state.

```bash
terraform -chdir=deploy/terraform/aws state show aws_vpc_security_group_ingress_rule.wireguard
```

Đối chiếu `cidr_ipv4` với Public IP Azure hiện tại kèm `/32`, `ip_protocol` là `udp`, `from_port` và `to_port` đều `51820`. Lệnh `state show` đọc dữ liệu Terraform đang lưu về resource. Ghi nhận kết quả apply thực tế trước khi đánh dấu hoàn thành rule AWS.

State local AWS đã ghi nhận resource `aws_vpc_security_group_ingress_rule.wireguard` sau lượt apply của người thực hành. Tiếp theo tạo rule inbound UDP 51820 trên NSG của Azure.

### 6.6. Khai báo rule WireGuard phía Azure bằng Terraform

Thực hiện trên laptop. Thêm biến sau vào `deploy/terraform/azure/variables.tf`.

```hcl
variable "wireguard_peer_cidr" {
  description = "Public IPv4 CIDR of the AWS WireGuard peer"
  type        = string
}
```

Đọc Elastic IP hiện tại của AWS bằng lệnh sau trong Git Bash.

```bash
terraform -chdir=deploy/terraform/aws output -raw aws_public_ip
```

Trong `deploy/terraform/azure/terraform.tfvars`, thêm giá trị bên dưới và thay placeholder bằng Elastic IP vừa đọc kèm `/32`.

```hcl
wireguard_peer_cidr = "<AWS_ELASTIC_IPV4>/32"
```

Hai root module AWS và Azure có biến cùng tên nhưng giá trị local khác nhau. Trên Azure, peer là máy AWS.

Thêm resource sau vào `deploy/terraform/azure/security.tf`.

```hcl
resource "azurerm_network_security_rule" "wireguard" {
  name                        = "wireguard-from-aws"
  priority                    = 330
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Udp"
  source_port_range           = "*"
  destination_port_range      = "51820"
  source_address_prefix       = var.wireguard_peer_cidr
  destination_address_prefix  = "*"
  resource_group_name         = azurerm_resource_group.standby.name
  network_security_group_name = azurerm_network_security_group.standby.name
}
```

Priority 330 tiếp nối các rule 300, 310 và 320 đang có. `source_address_prefix` giới hạn nguồn là AWS Elastic IP `/32`, `destination_port_range` giới hạn cổng đích 51820, còn `source_port_range` chấp nhận cổng nguồn bất kỳ. NSG này đã được gắn vào NIC của máy Azure.

Trong Git Bash trên laptop đã chọn đúng subscription, export lại biến môi trường khi cần rồi kiểm tra cấu hình và tạo saved plan.

```bash
export ARM_SUBSCRIPTION_ID="$(az account show --query id --output tsv | tr -d '\r')"

terraform -chdir=deploy/terraform/azure fmt
terraform -chdir=deploy/terraform/azure validate
terraform -chdir=deploy/terraform/azure plan -out=wireguard-azure.tfplan
```

Tổng kết dự kiến là `Plan: 1 to add, 0 to change, 0 to destroy.`, với resource mới `azurerm_network_security_rule.wireguard`. Đọc lại source CIDR, protocol Udp và destination port 51820 trong plan. Bước tiếp theo apply saved plan sau khi đã đối chiếu.

Sau khi thêm rule này, cấu hình Azure có tổng cộng 12 managed resource. Các con số 11 resource trong phần triển khai trước đó ghi nhận cấu hình tại thời điểm thực hành các bước đó.

### 6.7. Apply rule WireGuard phía Azure

Sau khi đối chiếu plan đúng mục 6.6, trong cùng tab Git Bash trên laptop đã chọn đúng subscription và export `ARM_SUBSCRIPTION_ID`, chạy saved plan.

```bash
terraform -chdir=deploy/terraform/azure apply wireguard-azure.tfplan
```

Mong đợi `Apply complete! Resources: 1 added, 0 changed, 0 destroyed.` Sau khi apply thành công, đọc resource từ Terraform state.

```bash
terraform -chdir=deploy/terraform/azure state show azurerm_network_security_rule.wireguard
```

Đối chiếu các thuộc tính của rule với cấu hình dự kiến.

- `name` bằng `wireguard-from-aws`, `priority` bằng `330`.
- `direction` bằng `Inbound`, `access` bằng `Allow`, `protocol` bằng `Udp`.
- `source_address_prefix` bằng Elastic IP AWS hiện tại kèm `/32`.
- `source_port_range` bằng `*`, `destination_port_range` bằng `51820`.
- `network_security_group_name` bằng `mcf-azure-nsg`.

Lệnh `state show` đọc thông tin resource đang được lưu trong Terraform state. State local Azure đã ghi nhận rule WireGuard, protocol `Udp`, source Elastic IP AWS `/32`, destination port `51820` và priority `330`. Các bước tiếp theo kiểm tra key và route trên hai máy, tạo file `wg0.conf`, bật tunnel rồi kiểm tra handshake và ping qua địa chỉ tunnel.

### 6.8. Kiểm tra key và route trước khi tạo cấu hình tunnel

Chạy các lệnh sau trong phiên SSH AWS, rồi chạy cùng các lệnh trong phiên SSH Azure.

```bash
sudo ls -l /etc/wireguard/private.key /etc/wireguard/public.key
sudo cat /etc/wireguard/public.key
ip -4 route
```

Hai file key cần thuộc root và có quyền `-rw-------`. Nếu key chưa được tạo, thực hiện bước 6.3 trên máy tương ứng. Public key của mỗi máy được dùng để điền vào phần peer của máy còn lại. Gắn nhãn rõ AWS/Azure khi ghi lại output.

Đọc bảng route hiện tại để đối chiếu dải tunnel đã chọn. Các route dự kiến thuộc mạng VPC AWS `10.29.0.0/16`, VNet Azure `10.30.0.0/16`, mạng Pod K3s mặc định `10.42.0.0/16` cùng default route và các route hệ thống. Đối chiếu cả các địa chỉ IP đã gán nếu có cấu hình mạng tùy chỉnh để xác nhận `10.200.29.1` và `10.200.29.2` phù hợp cho tunnel.

Ghi nhận public key và route trên từng máy trước khi tạo cấu hình AWS. Private key giữ tại máy đã tạo và được đọc cục bộ khi ghi cấu hình WireGuard.

Đã nhận kết quả kiểm tra Azure từ người thực hành. Hai file key thuộc root với quyền `600`, và đã đọc được public key. Route hiện tại gồm subnet `10.30.1.0/24`, mạng Pod `10.42.0.0/24`, default gateway `10.30.1.1` và các route hệ thống Azure. Các mạng cụ thể trong output tách biệt với địa chỉ tunnel `10.200.29.1/2` đã chọn.

Đã nhận kết quả kiểm tra AWS. Hai file key thuộc root với quyền `600`, và đã đọc được public key AWS. Route gồm subnet `10.29.1.0/24`, mạng Pod `10.42.0.0/24`, default gateway `10.29.1.1` và route DNS VPC. Các mạng cụ thể trong output cũng tách biệt với địa chỉ tunnel đã chọn. Hai public key được dùng khi cấu hình peer tương ứng.

### 6.9. Tạo file cấu hình WireGuard phía AWS

Chạy trong phiên SSH AWS với user `ubuntu`. Điền public key Azure đã đọc ở mục 6.8 và Public IP Azure hiện tại vào hai placeholder trong khối sau.

```bash
sudo sh -c '
set -eu
set -C
umask 077
mcf_private_key=$(cat /etc/wireguard/private.key)
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.200.29.1/32
ListenPort = 51820
MTU = 1420
PrivateKey = ${mcf_private_key}

[Peer]
PublicKey = <AZURE_PUBLIC_KEY>
AllowedIPs = 10.200.29.2/32
Endpoint = <AZURE_PUBLIC_IPV4>:51820
PersistentKeepalive = 25
EOF
'
```

Khối shell chạy bằng root và đọc private key tại máy AWS để ghi vào cấu hình. `umask 077` tạo file mode `600`, còn `set -C` dừng nếu file đích đã tồn tại. Khi nhận thông báo file tồn tại, kiểm tra cấu hình hiện có trước thao tác chỉnh sửa.

Ý nghĩa cấu hình được mô tả trong bảng sau.

| Trường | Chức năng trong cấu hình AWS |
|---|---|
| `Address` | Gán IP tunnel AWS `10.200.29.1/32` cho interface |
| `ListenPort` | Chọn cổng UDP nhận packet WireGuard |
| `MTU` | Giới hạn packet trong tunnel ở 1420 byte, dùng cùng giá trị trên hai máy cho đường truyền qua Internet |
| `PrivateKey` | Dùng private key AWS được đọc cục bộ để xác thực và thiết lập phiên mã hóa |
| `PublicKey` | Xác định peer Azure bằng public key của Azure |
| `AllowedIPs` | Định tuyến đích `10.200.29.2/32` tới peer Azure và giới hạn địa chỉ nguồn được nhận từ peer trong tunnel |
| `Endpoint` | Chỉ định Public IP và port UDP WireGuard của Azure |
| `PersistentKeepalive` | Gửi keepalive mỗi 25 giây để duy trì mapping qua NAT/firewall khi ít traffic |

Đọc phần cấu hình cần đối chiếu và quyền file bằng các lệnh dưới đây.

```bash
sudo sed '/^PrivateKey/d' /etc/wireguard/wg0.conf
sudo stat -c '%a %U:%G' /etc/wireguard/wg0.conf
```

Lệnh sed lọc dòng PrivateKey trước khi hiển thị. Mong đợi các giá trị tương ứng với AWS và peer Azure, cùng quyền file `600 root:root`. Người thực hành đã cung cấp kết quả cấu hình AWS khớp hướng dẫn và quyền file đúng dự kiến.

### 6.10. Tạo file cấu hình WireGuard phía Azure

Chạy trong phiên SSH Azure với user `azureuser`. Điền public key AWS đã đọc ở mục 6.8 và Elastic IP AWS hiện tại vào hai placeholder trong khối sau.

```bash
sudo sh -c '
set -eu
set -C
umask 077
mcf_private_key=$(cat /etc/wireguard/private.key)
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.200.29.2/32
ListenPort = 51820
MTU = 1420
PrivateKey = ${mcf_private_key}

[Peer]
PublicKey = <AWS_PUBLIC_KEY>
AllowedIPs = 10.200.29.1/32
Endpoint = <AWS_ELASTIC_IPV4>:51820
PersistentKeepalive = 25
EOF
'
```

Private key được đọc cục bộ từ máy Azure. `Address` là IP tunnel Azure `10.200.29.2/32`. Peer dùng public key AWS, địa chỉ tunnel `10.200.29.1/32` và endpoint Elastic IP AWS trên cổng UDP 51820. MTU và chu kỳ keepalive được đặt cùng giá trị với phía AWS.

Kiểm tra nội dung với dòng PrivateKey được lọc khỏi output và đọc quyền file.

```bash
sudo sed '/^PrivateKey/d' /etc/wireguard/wg0.conf
sudo stat -c '%a %U:%G' /etc/wireguard/wg0.conf
```

Mong đợi nội dung khớp cấu hình Azure cùng peer AWS và quyền `600 root:root`. Người thực hành đã cung cấp kết quả cấu hình Azure khớp hướng dẫn và quyền file đúng dự kiến.

### 6.11. Bật tunnel và kiểm tra kết nối hai chiều

Chạy hai lệnh sau trong phiên SSH AWS, rồi chạy cùng hai lệnh trong phiên SSH Azure. Hoàn tất bước bật ở cả hai máy trước khi thử ping.

```bash
sudo systemctl enable --now wg-quick@wg0
sudo systemctl is-active wg-quick@wg0
```

`enable` cấu hình khởi động cùng hệ điều hành, `--now` khởi chạy ngay service. Unit `wg-quick@wg0` gọi `wg-quick up wg0` để đọc `/etc/wireguard/wg0.conf`, tạo interface, gán địa chỉ và thêm route theo AllowedIPs. `is-active` dự kiến trả về `active`. Service có Type oneshot và RemainAfterExit, vì vậy khi xem status có thể thấy `active (exited)` sau khi lệnh cấu hình đã hoàn tất.

Trong phiên SSH AWS, kiểm tra kết nối tới địa chỉ tunnel Azure và đọc trạng thái WireGuard.

```bash
ping -c 4 -W 2 10.200.29.2
sudo wg show wg0
ip -4 route get 10.200.29.2
```

Trong phiên SSH Azure, kiểm tra chiều ngược lại.

```bash
ping -c 4 -W 2 10.200.29.1
sudo wg show wg0
ip -4 route get 10.200.29.1
```

Tiêu chí nghiệm thu bước kết nối được liệt kê dưới đây.

- Cả hai service trả về `active`.
- Ping nhận được phản hồi ở cả hai chiều, chạy lại lượt ping nếu cần chờ handshake ban đầu.
- Output `wg show wg0` có `latest handshake` gần thời điểm kiểm tra và transfer cả received/sent tăng khi gửi traffic.
- Route từ AWS tới `10.200.29.2` đi qua `dev wg0`, với source `10.200.29.1`. Route từ Azure tới `10.200.29.1` đi qua `dev wg0`, với source `10.200.29.2`.

Nếu service báo lỗi, lấy log trên đúng máy đang lỗi bằng lệnh sau.

```bash
sudo journalctl -u wg-quick@wg0 -n 60 --no-pager
```

Nếu service active nhưng thiếu handshake hoặc ping chưa có phản hồi, đối chiếu hai public key, endpoint Public IP, rule UDP 51820 của từng cloud và AllowedIPs trong cấu hình. Ghi nhận output thực tế trước khi đánh dấu tunnel đã nghiệm thu.

### 6.12. Kết quả nghiệm thu và luồng packet

Người thực hành đã cung cấp output kiểm tra hai chiều ngày 2026-11-11.

| Chiều kiểm tra | Kết quả ping | RTT trung bình | Route |
|---|---|---|---|
| Azure → AWS | 4 gửi, 4 nhận, mất gói 0% | 1.351 ms | Đích `10.200.29.1`, dev `wg0`, source `10.200.29.2` |
| AWS → Azure | 4 gửi, 4 nhận, mất gói 0% | 1.373 ms | Đích `10.200.29.2`, dev `wg0`, source `10.200.29.1` |

Hai phía đều có latest handshake gần thời điểm kiểm tra, đúng peer public key và endpoint. Transfer có cả received và sent. Tunnel đã được nghiệm thu qua handshake, route và ping hai chiều. Các giá trị RTT trong bảng là số đo ICMP của lượt kiểm tra này.

Khi Azure chạy `ping 10.200.29.1`, Linux tạo packet ICMP với IP nguồn tunnel `10.200.29.2` và IP đích tunnel `10.200.29.1`. Route đưa packet vào `wg0`. WireGuard chọn peer AWS qua AllowedIPs, sử dụng phiên mã hóa đã được thiết lập qua handshake và đóng gói packet trong UDP gửi tới public endpoint AWS. Public IP và port phía ngoài được cloud chuyển tiếp tới NIC của máy nhận.

AWS nhận UDP ở port 51820, WireGuard xác thực và giải mã, đối chiếu source tunnel với AllowedIPs của peer Azure rồi đưa packet vào hệ thống mạng tại `wg0`. Đích `10.200.29.1` là địa chỉ local của AWS, nên kernel trả lời ICMP. Packet trả lời đi qua tunnel theo chiều ngược lại. Quy trình tương tự áp dụng khi AWS chủ động ping Azure.

`latest handshake` thể hiện thời gian kể từ handshake thành công gần nhất. Các trường transfer là bộ đếm dữ liệu nhận/gửi của peer tại thời điểm đọc. `persistent keepalive` 25 giây duy trì mapping qua NAT/firewall khi ít traffic. Mỗi máy có số liệu riêng, và output được thu ở các thời điểm khác nhau.

Trong output ping, `icmp_seq` đánh số từng request, `time` là thời gian đi và về, còn `ttl` là TTL còn lại của packet trả lời bên trong tunnel. `56(84) bytes` tương ứng payload 56 byte, header ICMP 8 byte và IPv4 20 byte. Dòng phản hồi `64 bytes` tính phần ICMP gồm header và payload. Thống kê min/avg/max/mdev mô tả RTT của bốn lần thử.

## 7. Triển khai PostgreSQL trên hai cluster

### 7.1. Tạo namespace ứng dụng trên AWS

Namespace `issues` nhóm các tài nguyên của ứng dụng và database trong từng cluster. Bắt đầu trên AWS, sau đó dùng cùng manifest cho Azure. Lưu các manifest Kubernetes có thể tái sử dụng trong `deploy/kubernetes/` tại repository.

Trong Git Bash trên laptop, từ thư mục gốc project, tạo thư mục chứa manifest.

```bash
mkdir -p deploy/kubernetes
```

Tự tạo file `deploy/kubernetes/namespace.yaml` với nội dung sau.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: issues
```

`apiVersion` chọn phiên bản API core `v1`. `kind` chọn loại tài nguyên Namespace. `metadata.name` đặt tên namespace được tạo trong cluster.

Trong Git Bash trên laptop, lấy Public IP AWS hiện tại từ state và chuyển file lên home của user Ubuntu.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
scp -i ~/.ssh/mcf-lab deploy/kubernetes/namespace.yaml "ubuntu@$MCF_AWS_PUBLIC_IP:namespace.yaml"
```

`scp` sao chép file qua SSH. Lệnh trên đưa manifest từ laptop tới file `/home/ubuntu/namespace.yaml` trên EC2.

Trong phiên SSH AWS, áp dụng manifest và kiểm tra tài nguyên.

```bash
sudo k3s kubectl apply -f /home/ubuntu/namespace.yaml
sudo k3s kubectl get namespace issues
```

Lượt apply đầu tiên dự kiến hiện `namespace/issues created`. Lệnh get cần trả về namespace `issues` ở trạng thái `Active`. Khi áp dụng lại cùng cấu hình đã tồn tại, output có thể là `unchanged`.

`kubectl apply -f` đọc khai báo từ file và gửi yêu cầu tạo/cập nhật tới Kubernetes API của cluster hiện tại. Namespace này sẽ được dùng cho Secret, ConfigMap, Service, PVC, StatefulSet PostgreSQL và Deployment ứng dụng trong các bước tiếp theo.

Ghi nhận kết quả thực tế của namespace AWS trước khi chuyển sang áp dụng cùng manifest trên Azure.

### 7.2. Áp dụng namespace trên Azure

Dùng file `deploy/kubernetes/namespace.yaml` đã tạo ở mục 7.1. Trong Git Bash trên laptop tại thư mục gốc repository, lấy Public IP Azure hiện tại và copy manifest lên VM.

```bash
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"
scp -i ~/.ssh/mcf-lab deploy/kubernetes/namespace.yaml "azureuser@$MCF_AZURE_PUBLIC_IP:namespace.yaml"
```

File được đặt tại `/home/azureuser/namespace.yaml` trên Azure. Trong phiên SSH Azure, áp dụng và kiểm tra.

```bash
sudo k3s kubectl apply -f /home/azureuser/namespace.yaml
sudo k3s kubectl get namespace issues
```

Mong đợi lượt apply đầu tiên hiện `namespace/issues created` và namespace `issues` ở trạng thái `Active`. Khi áp dụng lại manifest đã có, output có thể là `unchanged`.

Hai cluster dùng cùng manifest để tạo namespace cùng tên. Mỗi namespace thuộc cluster đã nhận lệnh apply. Những tài nguyên ứng dụng và database sẽ được tạo trong namespace `issues` tương ứng của từng cloud.

Sau khi xác nhận namespace đã có trên cả AWS và Azure, bước tiếp theo chuẩn bị persistent storage cho PostgreSQL primary trên AWS.

### 7.3. Tạo StorageClass giữ dữ liệu trên AWS

StorageClass mô tả cách cấp phát persistent volume và policy thu hồi volume. Tạo class `local-path-retain` dùng provisioner local-path đã có trong K3s, với reclaim policy `Retain`.

Trên laptop, tự tạo file `deploy/kubernetes/storageclass.yaml` với nội dung sau.

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-path-retain
provisioner: rancher.io/local-path
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
```

`provisioner` chọn local-path-provisioner để cấp thư mục lưu dữ liệu trên ổ của node. Trong kiến trúc hiện tại, thư mục đó nằm trên filesystem của máy AWS, được lưu trên root EBS. `Retain` giữ lại PV và dữ liệu khi PVC bị xóa để có thể xử lý hoặc thu hồi thủ công. Policy này áp dụng ở vòng đời PV/PVC, còn dữ liệu trên ổ máy được quản lý thêm bằng backup và quy trình vòng đời hạ tầng.

`WaitForFirstConsumer` đợi có Pod sử dụng PVC để xác định node phù hợp trước khi cấp phát/binding volume. StorageClass là tài nguyên cấp cluster. Các PVC PostgreSQL ở bước tiếp theo sẽ tham chiếu rõ `storageClassName: local-path-retain`.

Trong Git Bash trên laptop tại thư mục gốc repository, copy manifest lên AWS.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
scp -i ~/.ssh/mcf-lab deploy/kubernetes/storageclass.yaml "ubuntu@$MCF_AWS_PUBLIC_IP:storageclass.yaml"
```

Trong phiên SSH AWS, áp dụng và kiểm tra StorageClass.

```bash
sudo k3s kubectl apply -f /home/ubuntu/storageclass.yaml
sudo k3s kubectl get storageclass local-path-retain
```

Lượt apply đầu tiên mong đợi `storageclass.storage.k8s.io/local-path-retain created`. Kết quả get cần có provisioner `rancher.io/local-path`, reclaim policy `Retain` và binding mode `WaitForFirstConsumer`.

Ghi nhận kết quả tạo StorageClass AWS trước khi tạo PVC dữ liệu cho PostgreSQL.

### 7.4. Tạo PVC dữ liệu PostgreSQL trên AWS

PVC (PersistentVolumeClaim) khai báo yêu cầu persistent storage cho workload. PostgreSQL sẽ tham chiếu PVC `postgres-data` trong namespace `issues` để lưu dữ liệu qua các lần tạo lại Pod.

Trên laptop, tự tạo file `deploy/kubernetes/postgres-pvc.yaml` với nội dung sau.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
  namespace: issues
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path-retain
  resources:
    requests:
      storage: 5Gi
```

`ReadWriteOnce` cho phép mount volume đọc/ghi trên một node. `storageClassName` chọn class Retain đã tạo ở mục 7.3. `storage: 5Gi` khai báo dung lượng yêu cầu 5 GiB trong Kubernetes. Local-path lưu dữ liệu trên filesystem chung của node và ghi nhận dung lượng yêu cầu trong metadata volume. Việc sử dụng dung lượng thực tế cần được theo dõi trên filesystem của máy.

Trong Git Bash trên laptop tại thư mục gốc repository, copy manifest lên AWS.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
scp -i ~/.ssh/mcf-lab deploy/kubernetes/postgres-pvc.yaml "ubuntu@$MCF_AWS_PUBLIC_IP:postgres-pvc.yaml"
```

Trong phiên SSH AWS, áp dụng và đọc trạng thái PVC.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-pvc.yaml
sudo k3s kubectl -n issues get pvc postgres-data
sudo k3s kubectl -n issues describe pvc postgres-data
```

Lượt apply đầu tiên mong đợi `persistentvolumeclaim/postgres-data created`. Khi đang chờ Pod sử dụng, PVC dự kiến có trạng thái `Pending`. Trong Events của describe, dự kiến có lý do `WaitForFirstConsumer` với nội dung đợi consumer trước khi binding.

StorageClass `WaitForFirstConsumer` trì hoãn provisioning/binding đến khi có Pod tham chiếu PVC và scheduler chọn node phù hợp. Khi triển khai StatefulSet PostgreSQL ở bước sau, PVC sẽ được kiểm tra chuyển sang `Bound` và PV có policy `Retain`.

Nếu describe xuất hiện lỗi khác như StorageClass chưa có, ghi lại Events để xử lý theo kết quả thực tế. Namespace `issues` cần Active và StorageClass `local-path-retain` cần tồn tại trên AWS trước khi triển khai các tài nguyên tiếp theo.

Người thực hành đã cung cấp output tạo PVC thành công trong namespace `issues`. PVC đang `Pending`, Used By là `<none>`, với event Normal `WaitForFirstConsumer`. Kết quả phù hợp với bước chuẩn bị trước khi tạo Pod PostgreSQL.

### 7.5. Tạo Secret đăng nhập PostgreSQL trên AWS

Secret `postgres-auth` lưu các tham số khởi tạo database để Pod PostgreSQL tham chiếu. Giữ tên database và user là `taskflow` theo cấu hình ứng dụng hiện tại, sinh mật khẩu ngẫu nhiên cho môi trường cloud.

Chạy các lệnh sau trong phiên SSH AWS. Tạo thư mục quản trị riêng cho root và file tham số có quyền `600`.

```bash
sudo install -d -m 700 /etc/mcf

sudo sh -c '
set -eu
set -C
umask 077
mcf_postgres_password=$(openssl rand -hex 32)
printf "POSTGRES_DB=taskflow\nPOSTGRES_USER=taskflow\nPOSTGRES_PASSWORD=%s\n" "$mcf_postgres_password" > /etc/mcf/postgres.env
'
```

`openssl rand -hex 32` sinh 32 byte ngẫu nhiên, biểu diễn bằng chuỗi hex 64 ký tự. `set -C` giữ file đã có khi chạy lại lệnh. File nằm trên VM AWS và được root quản lý. Ghi nội dung vào Secret bằng lệnh sau.

```bash
sudo k3s kubectl -n issues create secret generic postgres-auth \
  --from-env-file=/etc/mcf/postgres.env
```

`--from-env-file` đọc các dòng `KEY=value` và tạo các key tương ứng trong Secret thuộc namespace `issues`. Lượt tạo đầu tiên mong đợi `secret/postgres-auth created`. Khi Secret đã tồn tại, kiểm tra Secret hiện có và file tham số trước khi thực hiện cập nhật có chủ đích.

Đọc metadata và kích thước dữ liệu của Secret, cùng quyền file nguồn.

```bash
sudo k3s kubectl -n issues describe secret postgres-auth
sudo stat -c '%a %U:%G' /etc/mcf/postgres.env
```

Mong đợi Secret type `Opaque`, ba key `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, kích thước tương ứng 8, 8 và 64 byte, cùng quyền file `600 root:root`. Lệnh describe hiển thị tên key và kích thước dữ liệu để kiểm tra. Người thực hành đã cung cấp output Secret Opaque trong namespace issues với đúng ba key và kích thước dữ liệu dự kiến.

### 7.6. Tạo ConfigMap tham số PostgreSQL phía AWS

ConfigMap `postgres-config` chứa cấu hình PostgreSQL để mount vào Pod ở bước triển khai StatefulSet. Trên laptop, tự tạo file `deploy/kubernetes/postgres-config-aws.yaml` với nội dung sau.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-config
  namespace: issues
data:
  postgresql.conf: |
    listen_addresses = '127.0.0.1,10.200.29.1'
    port = 5432
    wal_level = replica
    max_wal_senders = 10
    wal_keep_size = '128MB'
    hot_standby = on
    password_encryption = 'scram-sha-256'
```

`postgresql.conf` là key trong ConfigMap. Dấu `|` giữ nội dung nhiều dòng thành một chuỗi để mount thành file cấu hình trong Pod.

| Tham số | Chức năng |
|---|---|
| `listen_addresses` | Nhận kết nối TCP trên loopback và IP WireGuard AWS |
| `port` | Chọn cổng TCP PostgreSQL 5432 |
| `wal_level` | Ghi thông tin WAL cần cho physical replication |
| `max_wal_senders` | Cho phép tối đa 10 kết nối WAL sender, phục vụ standby và streaming base backup |
| `wal_keep_size` | Giữ tối thiểu 128 MB WAL cũ phục vụ standby |
| `hot_standby` | Cho phép truy vấn đọc khi máy chạy trong chế độ standby |
| `password_encryption` | Chọn SCRAM-SHA-256 cho mật khẩu được thiết lập mới |

Pod PostgreSQL ở bước StatefulSet sẽ dùng mạng của node để có thể bind vào IP `wg0` đã chuẩn bị. Vai trò database được xác định bằng trạng thái data directory và quy trình khởi tạo/clone.

Trong Git Bash trên laptop tại thư mục gốc repository, copy file lên AWS.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
scp -i ~/.ssh/mcf-lab deploy/kubernetes/postgres-config-aws.yaml "ubuntu@$MCF_AWS_PUBLIC_IP:postgres-config-aws.yaml"
```

Trong phiên SSH AWS, áp dụng và kiểm tra ConfigMap.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-config-aws.yaml
sudo k3s kubectl -n issues get configmap postgres-config
```

Lượt đầu mong đợi `configmap/postgres-config created`, còn lệnh get hiển thị ConfigMap có DATA bằng 1. Bước tiếp theo bổ sung các quy tắc xác thực `pg_hba.conf` vào ConfigMap trước khi triển khai Pod PostgreSQL.

### 7.7. Bổ sung pg_hba.conf cho AWS

`pg_hba.conf` định nghĩa các kết nối được phép đăng nhập theo loại kết nối, database, user, địa chỉ nguồn và phương thức xác thực. Trên laptop, cập nhật file `deploy/kubernetes/postgres-config-aws.yaml` thành nội dung sau.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-config
  namespace: issues
data:
  postgresql.conf: |
    listen_addresses = '127.0.0.1,10.200.29.1'
    port = 5432
    hba_file = '/etc/postgresql/pg_hba.conf'
    wal_level = replica
    max_wal_senders = 10
    wal_keep_size = '128MB'
    hot_standby = on
    password_encryption = 'scram-sha-256'
  pg_hba.conf: |
    local all taskflow trust
    host all all 127.0.0.1/32 scram-sha-256
    host taskflow taskflow 10.42.0.0/16 scram-sha-256
    host taskflow taskflow 10.200.29.1/32 scram-sha-256
    host taskflow taskflow 10.200.29.2/32 scram-sha-256
    host replication replicator 10.200.29.2/32 scram-sha-256
```

`hba_file` chỉ định đường dẫn file xác thực sẽ được mount từ ConfigMap. Hai key `postgresql.conf` và `pg_hba.conf` cùng cấp dưới `data`.

Rule `local all taskflow trust` cho phép user database taskflow đăng nhập qua Unix socket tại máy, phục vụ khởi tạo và quản trị trong container. Quyền sử dụng socket local dựa trên quyền truy cập hệ điều hành/container, nên các thao tác quản trị cần dùng đúng tài khoản và phạm vi đã được cấp quyền.

Các rule `host` áp dụng cho TCP và dùng SCRAM-SHA-256. Rule loopback cho kết nối local TCP, rule mạng Pod cho ứng dụng trong cluster, hai rule tunnel cho user taskflow vào database taskflow qua địa chỉ WireGuard. Rule cuối cho kết nối physical replication bằng role replicator từ Azure `10.200.29.2/32`. Role và mật khẩu replicator được tạo ở bước chuẩn bị replication tiếp theo.

PostgreSQL xét rule theo thứ tự và chọn rule đầu tiên khớp kết nối. Việc xác thực sẽ dùng phương thức của rule đã chọn. Các địa chỉ nguồn trong file là IP bên trong tunnel hoặc mạng Pod, phù hợp với kết nối PostgreSQL sau khi WireGuard giải mã.

Trong Git Bash trên laptop, copy lại file đã cập nhật lên AWS.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
scp -i ~/.ssh/mcf-lab deploy/kubernetes/postgres-config-aws.yaml "ubuntu@$MCF_AWS_PUBLIC_IP:postgres-config-aws.yaml"
```

Trong phiên SSH AWS, cập nhật và đọc ConfigMap.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-config-aws.yaml
sudo k3s kubectl -n issues get configmap postgres-config
sudo k3s kubectl -n issues describe configmap postgres-config
```

Mong đợi apply hiện `configured` và ConfigMap có DATA bằng 2. Nội dung describe cần có cả `postgresql.conf` và `pg_hba.conf` theo cấu hình trên. Bước này chuẩn bị dữ liệu cấu hình cho StatefulSet sẽ được triển khai sau.

### 7.8. Tạo headless Service cho StatefulSet PostgreSQL

Service `postgres-headless` được dùng làm governing Service của StatefulSet PostgreSQL. StatefulSet ở bước tiếp theo sẽ tham chiếu tên này qua trường `serviceName` để thiết lập định danh mạng của Pod.

Trên laptop, tự tạo file `deploy/kubernetes/postgres-headless.yaml` với nội dung sau.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres-headless
  namespace: issues
spec:
  clusterIP: None
  selector:
    app: postgres
  ports:
    - name: postgres
      protocol: TCP
      port: 5432
      targetPort: 5432
```

`clusterIP: None` tạo headless Service. Kubernetes dùng thông tin endpoint của các Pod được selector chọn để cung cấp DNS cho Service. Selector `app: postgres` sẽ khớp label của Pod trong StatefulSet. Port khai báo giao thức TCP và cổng PostgreSQL 5432.

Trong thiết kế dùng hostNetwork và PostgreSQL bind IP WireGuard, Service `postgres` cho kết nối ứng dụng sẽ được cấu hình với endpoint IP tunnel ở bước riêng. Headless Service tại bước này đảm nhiệm định danh mạng của StatefulSet.

Trong Git Bash trên laptop tại thư mục gốc repository, copy manifest lên AWS.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
scp -i ~/.ssh/mcf-lab deploy/kubernetes/postgres-headless.yaml "ubuntu@$MCF_AWS_PUBLIC_IP:postgres-headless.yaml"
```

Trong phiên SSH AWS, tạo và kiểm tra Service.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-headless.yaml
sudo k3s kubectl -n issues get service postgres-headless
```

Lượt đầu mong đợi `service/postgres-headless created`. Output get cần có TYPE `ClusterIP`, CLUSTER-IP `None` và PORT(S) `5432/TCP`. Bước tiếp theo tạo StatefulSet sử dụng PVC, Secret, ConfigMap và governing Service đã chuẩn bị.

### 7.9. Chạy PostgreSQL primary trên AWS bằng StatefulSet

Tạo StatefulSet một replica sử dụng các tài nguyên đã chuẩn bị. Image được chọn là PostgreSQL 17 trên Debian Bookworm, ghim digest để dùng lại cùng image khi triển khai Azure. Metadata registry đã đối chiếu ngày 2026-11-12 cho biết PG_VERSION `17.11-1.pgdg12+2`.

Trên laptop, tự tạo file `deploy/kubernetes/postgres-aws.yaml` với nội dung sau.

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: issues
spec:
  serviceName: postgres-headless
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet
      terminationGracePeriodSeconds: 60
      containers:
        - name: postgres
          image: postgres:17-bookworm@sha256:665dc7b37ac52a17e298511414c21d23ffa4e6a6ef6225b3e5d59c7afb35e994
          args: ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]
          envFrom:
            - secretRef:
                name: postgres-auth
          env:
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 1Gi
          startupProbe:
            exec:
              command: ["pg_isready", "-h", "10.200.29.1", "-U", "taskflow", "-d", "taskflow"]
            periodSeconds: 5
            timeoutSeconds: 5
            failureThreshold: 60
          readinessProbe:
            exec:
              command: ["pg_isready", "-h", "10.200.29.1", "-U", "taskflow", "-d", "taskflow"]
            periodSeconds: 5
            timeoutSeconds: 5
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
            - name: config
              mountPath: /etc/postgresql
              readOnly: true
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: postgres-data
        - name: config
          configMap:
            name: postgres-config
```

StatefulSet tạo Pod `postgres-0`. `serviceName` tham chiếu governing Service. Selector và label `app: postgres` phải khớp nhau. `hostNetwork` cho Pod dùng mạng node để bind vào IP WireGuard `10.200.29.1`, còn `ClusterFirstWithHostNet` giữ cơ chế phân giải DNS Kubernetes cho Pod dùng host network.

`envFrom` lấy ba biến khởi tạo từ Secret postgres-auth. `PGDATA` đặt data directory trong PVC đã mount. Image chính thức thực hiện initdb khi data directory trống và thiết lập quyền data directory trước khi chạy PostgreSQL bằng user hệ điều hành postgres. Tham số config_file trỏ tới file từ ConfigMap.

Requests dành tài nguyên để scheduler bố trí Pod, limits giới hạn CPU và bộ nhớ container. Startup probe cho phép thời gian khởi tạo trước khi readiness probe hoạt động. Hai probe kiểm tra PostgreSQL nhận kết nối qua IP tunnel. Việc kiểm tra role, đăng nhập và đọc/ghi SQL sẽ được thực hiện bằng các lệnh SQL sau khi Pod sẵn sàng.

Trong Git Bash trên laptop, copy file lên AWS.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
scp -i ~/.ssh/mcf-lab deploy/kubernetes/postgres-aws.yaml "ubuntu@$MCF_AWS_PUBLIC_IP:postgres-aws.yaml"
```

Trong phiên SSH AWS, áp dụng và đợi StatefulSet sẵn sàng.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-aws.yaml
sudo k3s kubectl -n issues rollout status statefulset/postgres --timeout=600s
sudo k3s kubectl -n issues get pod postgres-0 -o wide
sudo k3s kubectl -n issues get pvc postgres-data
```

Mong đợi StatefulSet được tạo, Pod postgres-0 đạt `1/1 Running` và PVC postgres-data chuyển sang `Bound`. Việc tạo Pod tham chiếu PVC kích hoạt provisioning theo WaitForFirstConsumer.

Nếu rollout báo lỗi hoặc timeout, lấy thông tin trên đúng Pod để xử lý.

```bash
sudo k3s kubectl -n issues describe pod postgres-0
sudo k3s kubectl -n issues logs postgres-0 --tail=80
```

Người thực hành đã cung cấp kết quả rollout hoàn tất, Pod postgres-0 đạt `1/1 Running` với 0 restart. PVC postgres-data đã `Bound`, dung lượng khai báo 5 GiB, access mode RWO và StorageClass local-path-retain. Pod hiển thị IP node AWS `10.29.1.8` do sử dụng hostNetwork.

### 7.10. Xác nhận role và cấu hình PostgreSQL AWS bằng SQL

Chạy trong phiên SSH AWS. Dùng kubectl exec để chạy psql bên trong container PostgreSQL và đọc trạng thái database.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -U taskflow -d taskflow -P pager=off -c \
  "SELECT current_database(), current_user, pg_is_in_recovery() AS in_recovery, current_setting('transaction_read_only') AS read_only;"
```

Mong đợi database taskflow, user taskflow, in_recovery `f` và read_only `off`. Hàm pg_is_in_recovery trả false khi server đang hoạt động ngoài chế độ recovery. Trong topology hiện tại, đây là PostgreSQL primary. Giá trị transaction_read_only off cho biết giao dịch của phiên hiện tại được phép thực hiện các thao tác ghi theo quyền của user.

Lệnh exec chạy psql qua Unix socket trong container, sử dụng rule local taskflow đã khai báo trong pg_hba.conf. Dấu `--` kết thúc các tùy chọn kubectl, phần phía sau là chương trình và tham số chạy trong container. `-U` chọn user database, `-d` chọn database và `-c` truyền câu SQL.

Đọc các cấu hình PostgreSQL đang có hiệu lực.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -U taskflow -d taskflow -P pager=off -c \
  "SHOW listen_addresses; SHOW wal_level; SHOW hba_file;"
```

Mong đợi listen_addresses `127.0.0.1,10.200.29.1`, wal_level `replica` và hba_file `/etc/postgresql/pg_hba.conf`.

Kiểm tra policy của PV đã cấp cho PVC.

```bash
sudo k3s kubectl get pv
```

Đối chiếu PV có CLAIM `issues/postgres-data`, STATUS Bound, RECLAIM POLICY Retain và STORAGECLASS local-path-retain. Người thực hành đã cung cấp kết quả database/user taskflow, in_recovery f và read_only off. Cấu hình hiệu lực khớp các giá trị trên, PV Bound có policy Retain và claim issues/postgres-data.

Database taskflow được image PostgreSQL chính thức tạo trong lần khởi động đầu tiên khi data directory trống. StatefulSet đưa các key từ Secret postgres-auth vào biến môi trường của container bằng envFrom. Entrypoint đọc POSTGRES_USER=taskflow, POSTGRES_DB=taskflow và POSTGRES_PASSWORD để khởi tạo hệ database, tạo role và database tương ứng trước khi chạy server.

Data directory được đặt tại `/var/lib/postgresql/data/pgdata`, nằm trong volume của PVC postgres-data trên root EBS AWS. Khi khởi động lại Pod với volume đã được khởi tạo, PostgreSQL tiếp tục sử dụng data directory đó. Các câu SQL ở mục này đọc metadata, trạng thái và cấu hình sẵn có của PostgreSQL. Schema nghiệp vụ của ứng dụng được đưa vào database ở bước thực hành tiếp theo.

### 7.11. Khởi tạo schema ứng dụng trên AWS

Dùng hai file SQL hiện có của project để tạo cấu trúc database. `database/schema/control.sql` tạo bảng điều khiển quyền ghi ứng dụng, còn `database/schema/issues.sql` tạo các bảng nghiệp vụ và bảng phục vụ đo đạc.

Trong Git Bash trên laptop tại thư mục gốc repository, copy hai file lên home của user Ubuntu trên AWS.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
scp -i ~/.ssh/mcf-lab \
  database/schema/control.sql \
  database/schema/issues.sql \
  "ubuntu@$MCF_AWS_PUBLIC_IP:"
```

Hai file được đặt tại `/home/ubuntu/control.sql` và `/home/ubuntu/issues.sql`. Trong phiên SSH AWS, đưa nội dung hai file vào psql bên trong Pod PostgreSQL.

```bash
cat /home/ubuntu/control.sql /home/ubuntu/issues.sql | \
  sudo k3s kubectl -n issues exec -i postgres-0 -- \
  psql -X -U taskflow -d taskflow -v ON_ERROR_STOP=1 \
    --single-transaction -f -
```

`cat` ghép nội dung hai file theo thứ tự. `exec -i` giữ stdin để chuyển SQL vào container. `-f -` yêu cầu psql đọc SQL từ stdin, `-X` dùng cấu hình phiên mặc định, `ON_ERROR_STOP=1` dừng khi gặp lỗi SQL, còn `--single-transaction` gom cả lượt thực thi vào một transaction. Khi có lỗi, transaction được rollback. Khi thành công, các lệnh được commit cùng nhau.

Lượt khởi tạo đầu tiên dự kiến có các dòng CREATE TABLE, CREATE INDEX, INSERT cùng BEGIN/COMMIT. Các câu CREATE IF NOT EXISTS và INSERT ON CONFLICT trong hai file hỗ trợ áp dụng lại cùng khai báo lên schema đã có.

Kiểm tra danh sách bảng và trạng thái quyền ghi của ứng dụng.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c '\dt public.*'

sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT singleton, writes_enabled FROM app_control;"
```

Mong đợi sáu bảng thuộc user taskflow.

| Bảng | Chức năng |
|---|---|
| app_control | Cờ cho phép ghi ứng dụng, phục vụ quy trình chuyển writer |
| issues | Các issue nghiệp vụ |
| comments | Bình luận gắn với issue |
| issue_history | Lịch sử thay đổi issue |
| save_requests | Lưu request và kết quả để xử lý retry |
| probe_pings | Lưu các bản ghi probe phục vụ thí nghiệm và kiểm tra mất dữ liệu |

Trên database mới, app_control có một dòng singleton `t`, writes_enabled `t`. Người thực hành đã cung cấp output đủ sáu bảng public thuộc user taskflow và app_control có đúng một dòng singleton t, writes_enabled t.

### 7.12. Tạo role nhận WAL cho standby

Role `replicator` được dùng cho kết nối từ PostgreSQL Azure tới AWS khi tạo base backup và nhận WAL. Rule cho role này từ IP tunnel Azure `10.200.29.2/32` đã được chuẩn bị trong pg_hba.conf.

Trong phiên SSH AWS, tạo role bằng user quản trị database hiện tại.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -v ON_ERROR_STOP=1 -c \
  "CREATE ROLE replicator WITH LOGIN REPLICATION;"
```

Mong đợi `CREATE ROLE`. `LOGIN` cho phép role dùng để đăng nhập, còn `REPLICATION` cấp quyền kết nối replication và thực hiện các thao tác replication được PostgreSQL hỗ trợ. Role được tạo ở phạm vi PostgreSQL instance.

Đọc các thuộc tính của role vừa tạo.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT rolname, rolcanlogin, rolreplication, rolsuper FROM pg_roles WHERE rolname = 'replicator';"
```

Mong đợi một dòng role replicator với rolcanlogin `t`, rolreplication `t`, rolsuper `f`. Nếu role đã có từ lần thực hành trước, đọc các thuộc tính hiện tại trước khi thực hiện thay đổi theo cấu hình mong muốn.

Bước tiếp theo sinh và gán mật khẩu cho role replicator, chuẩn bị thông tin xác thực dùng khi dựng standby Azure và kiểm tra kết nối replication qua WireGuard.

### 7.13. Sinh và gán mật khẩu replication trên AWS

Chạy trong phiên SSH AWS. Sinh mật khẩu ngẫu nhiên và lưu thông tin replication trong file root quản lý.

```bash
sudo sh -c '
set -eu
set -C
umask 077
mcf_replication_password=$(openssl rand -hex 32)
printf "REPLICATION_USER=replicator\nREPLICATION_PASSWORD=%s\n" "$mcf_replication_password" > /etc/mcf/replication.env
'
```

Mật khẩu gồm 64 ký tự hex. File `/etc/mcf/replication.env` có quyền `600`, thuộc root, trong thư mục quản trị đã tạo ở mục 7.5. `set -C` bảo vệ file hiện có khi chạy lại lệnh. Khi file đã tồn tại, dùng nội dung đã lưu cho bước gán mật khẩu tiếp theo.

Đọc mật khẩu từ file và chuyển qua stdin vào Pod. Shell trong container đọc giá trị đó vào biến môi trường, psql lấy biến qua lệnh getenv để thực hiện ALTER ROLE.

```bash
sudo sh -c '
set -eu
. /etc/mcf/replication.env
printf "%s\n" "$REPLICATION_PASSWORD"
' | sudo k3s kubectl -n issues exec -i postgres-0 -- \
  bash -ec "IFS= read -r REPLICATION_PASSWORD
export REPLICATION_PASSWORD
psql -X -U taskflow -d taskflow -v ON_ERROR_STOP=1 <<'SQL'
\getenv repl_password REPLICATION_PASSWORD
ALTER ROLE replicator PASSWORD :'repl_password';
SQL"
```

Mong đợi `ALTER ROLE`. `read -r` đọc một dòng từ stdin, `export` đưa giá trị vào môi trường của psql. Lệnh `\getenv` tạo biến psql repl_password, còn cú pháp `:'repl_password'` trích dẫn giá trị thành SQL literal. PostgreSQL lưu thông tin mật khẩu theo cấu hình password_encryption đang có hiệu lực.

Kiểm tra thuộc tính role và định dạng mật khẩu bằng kết quả boolean.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT rolname, rolcanlogin, rolreplication, rolpassword LIKE 'SCRAM-SHA-256%' AS scram_password FROM pg_authid WHERE rolname = 'replicator';"
```

Mong đợi role replicator với rolcanlogin t, rolreplication t và scram_password t. Người thực hành đã cung cấp kết quả metadata đúng cả ba giá trị. File thông tin replication sẽ được dùng khi chuẩn bị thông tin xác thực cho standby Azure.

### 7.14. Chuẩn bị namespace và storage PostgreSQL trên Azure

Dùng lại ba manifest namespace, StorageClass và PVC đã áp dụng trên AWS. Mỗi cluster quản lý các resource và volume được tạo tại môi trường tương ứng.

Trong Git Bash trên laptop tại thư mục gốc repository, copy các file lên Azure.

```bash
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/namespace.yaml \
  deploy/kubernetes/storageclass.yaml \
  deploy/kubernetes/postgres-pvc.yaml \
  "azureuser@$MCF_AZURE_PUBLIC_IP:"
```

Trong phiên SSH Azure, áp dụng lần lượt namespace, StorageClass và PVC.

```bash
sudo k3s kubectl apply -f /home/azureuser/namespace.yaml
sudo k3s kubectl apply -f /home/azureuser/storageclass.yaml
sudo k3s kubectl apply -f /home/azureuser/postgres-pvc.yaml
```

Namespace đã được tạo ở mục 7.2 có thể hiện unchanged. Kiểm tra các tài nguyên Azure.

```bash
sudo k3s kubectl get namespace issues
sudo k3s kubectl get storageclass local-path-retain
sudo k3s kubectl -n issues get pvc postgres-data
```

Mong đợi namespace issues Active, StorageClass local-path-retain có policy Retain và binding mode WaitForFirstConsumer. PVC postgres-data dự kiến Pending trong lúc chờ Pod sử dụng. Khi Pod standby được tạo, local-path-provisioner cấp volume trên ổ của VM Azure và PVC chuyển sang Bound.

Người thực hành đã cung cấp output Azure có namespace issues Active, StorageClass local-path-retain dùng Retain và WaitForFirstConsumer, PVC postgres-data Pending. Storage đã sẵn sàng cho bước tạo Pod sử dụng volume.

### 7.15. Tạo Secret replication trên Azure

Azure cần thông tin đăng nhập của role replicator đã tạo trên PostgreSQL AWS. Tạo Secret postgres-replication trong namespace issues của cluster Azure để bước clone và streaming sử dụng cùng thông tin xác thực.

Mở Git Bash trên laptop tại thư mục gốc repository, lấy Public IP hiện tại của hai máy.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"
```

Đọc file replication.env từ AWS vào biến của phiên shell, rồi chuyển nội dung qua SSH để tạo Secret trên Azure.

```bash
MCF_REPLICATION_ENV="$(ssh -i ~/.ssh/mcf-lab "ubuntu@$MCF_AWS_PUBLIC_IP" \
  'sudo cat /etc/mcf/replication.env')" &&
  printf '%s\n' "$MCF_REPLICATION_ENV" | \
  ssh -i ~/.ssh/mcf-lab "azureuser@$MCF_AZURE_PUBLIC_IP" \
    'sudo k3s kubectl -n issues create secret generic postgres-replication --from-env-file=/dev/stdin'

unset MCF_REPLICATION_ENV
```

Private key có passphrase sẽ yêu cầu mở khóa cho từng kết nối SSH khi key chưa được nạp vào ssh-agent. Hai kết nối chạy lần lượt. Dấu && chỉ thực hiện phần gửi khi lệnh đọc từ AWS thành công. Biến MCF_REPLICATION_ENV giữ nội dung trong bộ nhớ của shell, printf chuyển nội dung vào pipe, còn unset bỏ biến sau thao tác.

Trên Azure, /dev/stdin là luồng đầu vào của tiến trình kubectl. Tùy chọn --from-env-file đọc hai dòng KEY=value để tạo hai key trong Secret. Luồng chuyển thông tin quản trị đi theo AWS → SSH → laptop → SSH → Azure. Khi PostgreSQL standby chạy, dữ liệu database và WAL sẽ truyền qua tunnel WireGuard giữa hai cloud.

Mong đợi output sau.

```text
secret/postgres-replication created
```

Trong phiên SSH Azure, kiểm tra metadata và kích thước các key.

```bash
sudo k3s kubectl -n issues describe secret postgres-replication
```

Mong đợi Secret Opaque có REPLICATION_USER 10 bytes và REPLICATION_PASSWORD 64 bytes. Bước này được nghiệm thu khi người thực hành cung cấp kết quả describe tương ứng.

### 7.16. Tạo ConfigMap PostgreSQL phía Azure

Tạo file deploy/kubernetes/postgres-config-azure.yaml trên laptop với nội dung sau.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-config
  namespace: issues
data:
  postgresql.conf: |
    listen_addresses = '127.0.0.1,10.200.29.2'
    port = 5432
    hba_file = '/etc/postgresql/pg_hba.conf'
    wal_level = replica
    max_wal_senders = 10
    wal_keep_size = '128MB'
    hot_standby = on
    password_encryption = 'scram-sha-256'
  pg_hba.conf: |
    local all taskflow trust
    host all all 127.0.0.1/32 scram-sha-256
    host taskflow taskflow 10.42.0.0/16 scram-sha-256
    host taskflow taskflow 10.200.29.1/32 scram-sha-256
    host taskflow taskflow 10.200.29.2/32 scram-sha-256
    host replication replicator 10.200.29.1/32 scram-sha-256
```

listen_addresses chứa IP WireGuard của Azure là 10.200.29.2. hot_standby cho phép truy vấn chỉ đọc trong lúc PostgreSQL phục hồi và replay WAL. max_wal_senders bằng phía AWS để đáp ứng yêu cầu cấu hình standby. Dòng replication trong pg_hba.conf cho phép replicator từ IP WireGuard AWS, phục vụ luồng rejoin AWS sau khi Azure được promote ở giai đoạn failback.

Hai cluster độc lập có thể sử dụng cùng tên ConfigMap postgres-config trong namespace issues. Tên file trên laptop giúp chọn cấu hình phù hợp khi apply vào từng cluster. Cấu hình kết nối đi ra từ Azure đến AWS sẽ được tạo ở bước pg_basebackup -R cùng standby.signal.

Trong Git Bash trên laptop tại thư mục gốc repository, copy manifest lên Azure.

```bash
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/postgres-config-azure.yaml \
  "azureuser@$MCF_AZURE_PUBLIC_IP:"
```

Trong phiên SSH Azure, áp dụng và kiểm tra ConfigMap.

```bash
sudo k3s kubectl apply -f /home/azureuser/postgres-config-azure.yaml
sudo k3s kubectl -n issues get configmap postgres-config
```

Mong đợi ConfigMap postgres-config có DATA bằng 2, tương ứng postgresql.conf và pg_hba.conf. Kiểm tra này xác nhận resource đã được lưu vào cluster. Sau khi tạo Pod, kiểm tra cấu hình hiệu lực bằng SQL như phía AWS.

Người thực hành đã cung cấp output Azure xác nhận ConfigMap postgres-config được tạo và DATA bằng 2.

### 7.17. Tạo headless Service PostgreSQL trên Azure

Dùng lại deploy/kubernetes/postgres-headless.yaml đã áp dụng trên AWS. Service này có clusterIP None và selector app postgres. StatefulSet Azure sẽ sử dụng tên postgres-headless tại trường serviceName để cung cấp định danh mạng ổn định cho Pod.

Trong Git Bash trên laptop tại thư mục gốc repository, copy manifest lên Azure.

```bash
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/postgres-headless.yaml \
  "azureuser@$MCF_AZURE_PUBLIC_IP:"
```

Trong phiên SSH Azure, áp dụng và kiểm tra Service.

```bash
sudo k3s kubectl apply -f /home/azureuser/postgres-headless.yaml
sudo k3s kubectl -n issues get service postgres-headless
```

Mong đợi Service postgres-headless có TYPE ClusterIP, CLUSTER-IP None và PORT(S) 5432/TCP. Giá trị None thể hiện đây là headless Service. Khi có Pod khớp selector, Kubernetes quản lý các endpoint tương ứng.

PostgreSQL dùng hostNetwork và lắng nghe trên loopback cùng IP WireGuard. Service dành cho ứng dụng sẽ được cấu hình riêng bằng EndpointSlice trỏ tới IP WireGuard Azure ở bước triển khai ứng dụng.

### 7.18. Chuẩn bị Secret đăng nhập database trên Azure

Full physical backup bằng pg_basebackup sao chép toàn bộ PostgreSQL database cluster, gồm các role và thông tin mật khẩu. Secret postgres-auth trên Azure cần giữ cùng POSTGRES_DB, POSTGRES_USER và POSTGRES_PASSWORD như AWS để cấu hình workload và ứng dụng khớp với dữ liệu được clone. Mật khẩu PostgreSQL có hiệu lực trên standby được kế thừa từ bản clone.

Trong Git Bash trên laptop tại thư mục gốc repository, lấy Public IP hiện tại của hai máy.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"
```

Chuyển nội dung file postgres.env trên AWS vào Secret postgres-auth của cluster Azure.

```bash
MCF_POSTGRES_ENV="$(ssh -i ~/.ssh/mcf-lab "ubuntu@$MCF_AWS_PUBLIC_IP" \
  'sudo cat /etc/mcf/postgres.env')" &&
  printf '%s\n' "$MCF_POSTGRES_ENV" | \
  ssh -i ~/.ssh/mcf-lab "azureuser@$MCF_AZURE_PUBLIC_IP" \
    'sudo k3s kubectl -n issues create secret generic postgres-auth --from-env-file=/dev/stdin'

unset MCF_POSTGRES_ENV
```

Cách truyền qua biến shell, pipe và SSH giống mục 7.15. Mong đợi secret/postgres-auth created. Private key có passphrase có thể yêu cầu mở khóa cho mỗi kết nối.

Trong phiên SSH Azure, kiểm tra metadata của hai Secret cần dùng khi triển khai standby.

```bash
sudo k3s kubectl -n issues describe secret postgres-auth
sudo k3s kubectl -n issues describe secret postgres-replication
```

Secret postgres-auth cần có POSTGRES_DB 8 bytes, POSTGRES_USER 8 bytes và POSTGRES_PASSWORD 64 bytes. Secret postgres-replication cần có REPLICATION_USER 10 bytes và REPLICATION_PASSWORD 64 bytes. Kiểm tra này xác nhận các key và kích thước dự kiến. Việc xác thực thực tế với AWS được kiểm tra khi chạy bước clone tiếp theo.

### 7.19. Chuẩn bị script clone database trên Azure

Tạo file deploy/kubernetes/postgres-clone-script.yaml trên laptop. ConfigMap này chứa script được Job clone gọi ở bước tiếp theo. Job sẽ mount PVC postgres-data và lấy biến môi trường từ Secret postgres-replication. PGDATA được Job đặt thành /var/lib/postgresql/data/pgdata, SOURCE_DB_HOST là IP WireGuard AWS.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-clone-script
  namespace: issues
data:
  clone.sh: |
    set -eu

    if [ -f "$PGDATA/PG_VERSION" ]; then
      test -f /var/lib/postgresql/data/.clone-complete
      echo "Existing completed clone found"
      exit 0
    fi

    install -d -o postgres -g postgres -m 700 "$PGDATA"
    test -z "$(ls -A "$PGDATA")"

    umask 077
    PGPASSFILE=/var/lib/postgresql/data/replication.pgpass
    printf '%s:5432:replication:%s:%s\n' \
      "$SOURCE_DB_HOST" "$REPLICATION_USER" "$REPLICATION_PASSWORD" \
      > "$PGPASSFILE"
    chown postgres:postgres "$PGPASSFILE"
    chmod 600 "$PGPASSFILE"

    gosu postgres pg_basebackup \
      -d "host=$SOURCE_DB_HOST port=5432 user=$REPLICATION_USER passfile=$PGPASSFILE application_name=mcf-azure-standby connect_timeout=10" \
      -D "$PGDATA" -R -X stream -c fast -w

    test "$(cat "$PGDATA/PG_VERSION")" = 17
    test -f "$PGDATA/standby.signal"
    touch /var/lib/postgresql/data/.clone-complete
    echo "Base backup completed"
```

set -e dừng script khi một lệnh kiểm tra hoặc clone lỗi, set -u yêu cầu các biến được tham chiếu đã được khai báo. Script kiểm tra marker .clone-complete khi gặp data directory đã có PG_VERSION. Với thư mục chuẩn bị clone mới, nội dung phải trống. Khi gặp dữ liệu dở dang, đọc log và kiểm tra PVC trước khi chọn phương án phục hồi.

Script tạo password file trên PVC với quyền 600, owner postgres. Mật khẩu được lấy từ Secret ở thời điểm Job chạy. Tham số passfile được đưa vào connection string để pg_basebackup -R ghi đường dẫn này vào cấu hình kết nối standby. Khi triển khai StatefulSet Azure, cùng PVC sẽ được mount tại cùng đường dẫn để PostgreSQL tiếp tục sử dụng password file.

pg_basebackup kết nối AWS qua WireGuard bằng role replicator. -D chọn data directory, -R tạo standby.signal và ghi thông tin kết nối vào postgresql.auto.conf, -X stream lấy WAL song song với base backup, -c fast yêu cầu checkpoint nhanh và -w dùng xác thực đã chuẩn bị qua password file. gosu chạy pg_basebackup dưới user hệ điều hành postgres. Marker .clone-complete được tạo sau khi lệnh clone thành công và hai kiểm tra cuối đạt yêu cầu.

Trong Git Bash trên laptop tại thư mục gốc repository, copy manifest lên Azure.

```bash
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/postgres-clone-script.yaml \
  "azureuser@$MCF_AZURE_PUBLIC_IP:"
```

Trong phiên SSH Azure, lưu script vào ConfigMap.

```bash
sudo k3s kubectl apply -f /home/azureuser/postgres-clone-script.yaml
sudo k3s kubectl -n issues get configmap postgres-clone-script
```

Mong đợi ConfigMap postgres-clone-script có DATA bằng 1. Lệnh apply lưu nội dung script, việc chạy pg_basebackup bắt đầu khi tạo Job ở bước tiếp theo.

### 7.20. Chạy Job clone PostgreSQL từ AWS sang Azure

Tạo file deploy/kubernetes/postgres-clone-azure.yaml trên laptop. Job dùng cùng image PostgreSQL đã cố định trên AWS, mount PVC postgres-data của Azure và chạy script clone.sh từ ConfigMap postgres-clone-script.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: postgres-clone
  namespace: issues
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 600
  template:
    spec:
      hostNetwork: true
      dnsPolicy: ClusterFirstWithHostNet
      restartPolicy: Never
      containers:
        - name: basebackup
          image: postgres:17-bookworm@sha256:665dc7b37ac52a17e298511414c21d23ffa4e6a6ef6225b3e5d59c7afb35e994
          command: ["bash", "/bootstrap/clone.sh"]
          envFrom:
            - secretRef:
                name: postgres-replication
          env:
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
            - name: SOURCE_DB_HOST
              value: "10.200.29.1"
          resources:
            requests:
              cpu: 200m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 1Gi
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
            - name: script
              mountPath: /bootstrap
              readOnly: true
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: postgres-data
        - name: script
          configMap:
            name: postgres-clone-script
```

hostNetwork cho Pod sử dụng mạng host Azure, gồm route qua wg0 đến 10.200.29.1. Kết nối đi qua tunnel với source 10.200.29.2, khớp rule replication trên PostgreSQL AWS. Secret cung cấp REPLICATION_USER và REPLICATION_PASSWORD cho script. PVC lưu bản sao dữ liệu để StatefulSet sử dụng tiếp sau khi Job hoàn tất.

restartPolicy Never kết thúc container khi script thoát. backoffLimit 0 đánh dấu Job thất bại khi Pod lỗi, giữ kết quả để kiểm tra trước khi chạy lại. activeDeadlineSeconds 600 giới hạn thời gian hoạt động của Job ở mức mười phút cho dữ liệu lab hiện tại. Khi Job thành công, Kubernetes ghi nhận completion và giữ Pod để đọc log.

Trong Git Bash trên laptop tại thư mục gốc repository, copy manifest lên Azure.

```bash
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/postgres-clone-azure.yaml \
  "azureuser@$MCF_AZURE_PUBLIC_IP:"
```

Trong phiên SSH Azure, tạo Job và theo dõi log.

```bash
sudo k3s kubectl apply -f /home/azureuser/postgres-clone-azure.yaml
sudo k3s kubectl -n issues logs -f job/postgres-clone --pod-running-timeout=180s
```

Lượt clone đầu tiên thành công cần có dòng Base backup completed. Kiểm tra trạng thái Job và PVC sau khi log kết thúc.

```bash
sudo k3s kubectl -n issues get job postgres-clone
sudo k3s kubectl -n issues get pvc postgres-data
```

Mong đợi Job COMPLETIONS 1/1 và PVC Bound. Đây là checkpoint hoàn thành bản sao ban đầu và các file cấu hình standby. Việc chạy PostgreSQL Azure và xác nhận WAL streaming liên tục được thực hiện ở bước StatefulSet tiếp theo.

Nếu Job thất bại hoặc Pod còn Pending, dùng metadata và log để xác định bước lỗi.

```bash
sudo k3s kubectl -n issues describe job postgres-clone
sudo k3s kubectl -n issues get pods -l job-name=postgres-clone
sudo k3s kubectl -n issues describe pods -l job-name=postgres-clone
```

Đối chiếu Secret, ConfigMap, trạng thái PVC, WireGuard và kết quả pg_basebackup trong log. Khi cần chạy lại một Job đã kết thúc, kiểm tra tình trạng bản clone trên PVC rồi xử lý nguyên nhân lỗi trước khi tạo lượt Job mới. Apply lại manifest của Job đã hoàn tất sẽ giữ Job hiện có.

Người thực hành đã cung cấp output Azure xác nhận Job postgres-clone Complete, COMPLETIONS 1/1, DURATION 27s. PVC postgres-data Bound với volume pvc-d333bc1a-f740-4fa0-bbc9-b65c3e13369e, dung lượng 5Gi, RWO và StorageClass local-path-retain.

### 7.21. Chạy PostgreSQL standby trên Azure bằng StatefulSet

Trong Git Bash trên laptop tại thư mục gốc repository, tạo manifest Azure từ manifest AWS đã có.

```bash
cp deploy/kubernetes/postgres-aws.yaml deploy/kubernetes/postgres-azure.yaml
```

Trong file postgres-azure.yaml, đổi địa chỉ ở cả startupProbe và readinessProbe từ 10.200.29.1 thành 10.200.29.2. Mỗi probe cần có command sau.

```yaml
              command: ["pg_isready", "-h", "10.200.29.2", "-U", "taskflow", "-d", "taskflow"]
```

Thêm command ngay dưới image của container postgres. Đoạn command và args sau khi chỉnh cần có nội dung sau.

```yaml
          command:
            - bash
            - -ec
            - |
              test -f /var/lib/postgresql/data/.clone-complete
              test "$(cat "$PGDATA/PG_VERSION")" = 17
              exec docker-entrypoint.sh "$@"
            - --
          args: ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]
```

Hai kiểm tra đầu xác nhận marker hoàn thành clone và major version 17 trên PVC. bash -ec chạy đoạn kiểm tra rồi exec gọi entrypoint chính thức của image. Dấu -- được dùng làm giá trị $0 của Bash, còn "$@" nhận các phần tử args. Entrypoint sử dụng data directory đã clone và khởi động PostgreSQL với ConfigMap Azure. standby.signal cùng primary_conninfo đã được pg_basebackup -R tạo sẽ đưa PostgreSQL vào chế độ standby và cấu hình kết nối về AWS.

StatefulSet tham chiếu Secret postgres-auth, ConfigMap postgres-config và PVC postgres-data của cluster Azure. Cùng đường dẫn mount dữ liệu giữ cho primary_conninfo tìm được replication.pgpass đã tạo bởi Job. Cơ chế kiểm tra vai trò khi reboot sau failover được bổ sung ở bước fencing/rejoin của giai đoạn phục hồi.

Copy manifest đã chỉnh lên Azure từ Git Bash trên laptop.

```bash
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/postgres-azure.yaml \
  "azureuser@$MCF_AZURE_PUBLIC_IP:"
```

Trong phiên SSH Azure, tạo StatefulSet và kiểm tra Pod.

```bash
sudo k3s kubectl apply -f /home/azureuser/postgres-azure.yaml
sudo k3s kubectl -n issues rollout status statefulset/postgres --timeout=180s
sudo k3s kubectl -n issues get pod postgres-0 -o wide
```

Mong đợi postgres-0 có READY 1/1 và STATUS Running trên node Azure. Với hostNetwork, IP của Pod là IP private host Azure. Truy vấn vai trò database trong Pod.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT pg_is_in_recovery() AS in_recovery, current_setting('transaction_read_only') AS read_only;"
```

Mong đợi in_recovery t và read_only on. Tiếp theo kiểm tra kết nối WAL receiver/sender và dữ liệu đã replay từ AWS. Nếu Pod gặp lỗi khởi động, đọc logs postgres-0 và describe pod để kiểm tra mount, file clone, password file và cấu hình PostgreSQL.

Người thực hành đã cung cấp output Azure xác nhận StatefulSet postgres rollout hoàn tất, Pod postgres-0 Running 1/1 với 0 restart trên node mcf-azure-standby, IP 10.30.1.4. SQL trả về in_recovery t và read_only on.

### 7.22. Kiểm tra WAL sender và receiver giữa hai cloud

Trong phiên SSH AWS, đọc trạng thái kết nối của standby từ PostgreSQL primary.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT application_name, client_addr, state, sync_state FROM pg_stat_replication;"
```

Mong đợi một dòng có application_name mcf-azure-standby, client_addr 10.200.29.2, state streaming và sync_state async. application_name được truyền từ bước pg_basebackup và ghi vào primary_conninfo. client_addr thể hiện địa chỉ WireGuard Azure mà AWS thấy trên kết nối replication. async là chế độ replication bất đồng bộ của lab.

Trong phiên SSH Azure, kiểm tra WAL receiver đang kết nối tới primary nào.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT status, sender_host, sender_port FROM pg_stat_wal_receiver;"
```

Mong đợi một dòng có status streaming, sender_host 10.200.29.1 và sender_port 5432. Azure chủ động mở kết nối TCP đến PostgreSQL AWS qua WireGuard. WAL sender phía AWS truyền WAL trên kết nối này, WAL receiver phía Azure nhận WAL để standby replay.

Checkpoint đạt khi hai phía cùng thể hiện trạng thái streaming với đúng IP WireGuard. Trạng thái này phản ánh kết nối tại thời điểm truy vấn. Kiểm chứng một thay đổi dữ liệu mới trên AWS được replay sang Azure được thực hiện ở bước tiếp theo.

Nếu kết quả trống hoặc khác dự kiến, đọc log PostgreSQL Azure để xác định trạng thái kết nối, xác thực hoặc WAL cần phục hồi.

```bash
sudo k3s kubectl -n issues logs postgres-0 --tail=60
```

Người thực hành đã xác nhận các kiểm tra WAL sender và receiver ở mục 7.22 cho kết quả đúng dự kiến.

### 7.23. Ghi trên AWS và kiểm tra dữ liệu được replay sang Azure

Dùng bảng probe_pings đã có trong schema để lưu bản ghi kiểm tra replication. Mỗi lần chạy tạo run_id mới bằng UUID ngẫu nhiên để đối chiếu đúng thay đổi vừa thực hiện.

Trong phiên SSH AWS, thêm một bản ghi rồi đọc các giá trị vừa được lưu.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -v ON_ERROR_STOP=1 -P pager=off -c \
  "INSERT INTO probe_pings (run_id, seq, environment)
   VALUES ('stage5-wal-' || gen_random_uuid()::text, 1, 'aws')
   RETURNING run_id, seq, environment, created_at;"
```

Ghi lại đầy đủ run_id từ output AWS, cùng seq, environment và created_at. gen_random_uuid tạo UUID ngẫu nhiên; phép nối chuỗi || thêm tiền tố stage5-wal-. RETURNING trả lại chính bản ghi vừa insert. psql mặc định autocommit cho lệnh này.

Trong phiên SSH Azure, thay DAN_RUN_ID_TU_AWS bằng đúng run_id vừa nhận rồi truy vấn.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT run_id, seq, environment, created_at
   FROM probe_pings
   WHERE run_id = 'DAN_RUN_ID_TU_AWS';"
```

Mong đợi một dòng có đủ bốn giá trị giống bản ghi AWS. environment vẫn là aws vì giá trị đó được lưu khi ghi trên primary và được replication chuyển sang standby. created_at là thời điểm tạo bản ghi ở AWS. Với replication bất đồng bộ, nếu truy vấn ngay cho 0 rows, chờ vài giây rồi chạy lại SELECT với cùng run_id.

Luồng nghiệm thu là INSERT trên AWS → PostgreSQL ghi WAL → truyền WAL qua WireGuard → Azure replay WAL → SELECT thấy bản ghi trên Azure. Kết quả này xác nhận dữ liệu mới đã được replay tại thời điểm kiểm tra. Các chỉ số mất acknowledged writes, RPO và failover được đo trong giai đoạn thí nghiệm tương ứng.

Người thực hành đã cung cấp kết quả SELECT trên Azure có run_id stage5-wal-30993431-b44b-49b2-971b-1755e6b73423, seq 1, environment aws và created_at 2026-11-12 15:37:59.460877+00. Bản ghi được tạo theo bước INSERT trên AWS rồi đọc từ standby Azure.

### 7.24. Tạo Service postgres cho ứng dụng trên hai cluster

Ứng dụng sẽ kết nối database bằng hostname postgres và port 5432 trong namespace issues. Tạo Service postgres ở mỗi cluster, sau đó cấu hình EndpointSlice riêng để ánh xạ đến IP WireGuard của PostgreSQL tại cloud tương ứng. Service postgres-headless đã tạo phục vụ định danh mạng của StatefulSet.

Tạo file deploy/kubernetes/postgres-service.yaml trên laptop với nội dung sau.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: issues
spec:
  ports:
    - name: postgres
      protocol: TCP
      port: 5432
      targetPort: 5432
```

Service dùng type ClusterIP mặc định. Kubernetes cấp địa chỉ IP nội bộ cho Service. Đích backend được quản lý bằng EndpointSlice thủ công ở bước tiếp theo, phù hợp với cấu hình PostgreSQL lắng nghe trên IP WireGuard. Tại AWS, đích là 10.200.29.1:5432. Tại Azure, đích là 10.200.29.2:5432.

Trong Git Bash trên laptop tại thư mục gốc repository, copy cùng manifest lên cả hai máy.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"

scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/postgres-service.yaml \
  "ubuntu@$MCF_AWS_PUBLIC_IP:"

scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/postgres-service.yaml \
  "azureuser@$MCF_AZURE_PUBLIC_IP:"
```

Trong phiên SSH AWS, tạo và kiểm tra Service.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-service.yaml
sudo k3s kubectl -n issues get service postgres
```

Trong phiên SSH Azure, tạo và kiểm tra Service.

```bash
sudo k3s kubectl apply -f /home/azureuser/postgres-service.yaml
sudo k3s kubectl -n issues get service postgres
```

Mong đợi Service postgres có TYPE ClusterIP, một CLUSTER-IP nội bộ và PORT(S) 5432/TCP trên mỗi cluster. Checkpoint này xác nhận Service đã được tạo. Kết nối database qua Service được nghiệm thu sau khi bổ sung EndpointSlice và chạy client trong namespace issues.

### 7.25. Ánh xạ Service postgres tới IP WireGuard bằng EndpointSlice

Tạo file deploy/kubernetes/postgres-endpoint-aws.yaml trên laptop với nội dung sau.

```yaml
apiVersion: discovery.k8s.io/v1
kind: EndpointSlice
metadata:
  name: postgres-wireguard
  namespace: issues
  labels:
    kubernetes.io/service-name: postgres
    endpointslice.kubernetes.io/managed-by: cluster-admins
addressType: IPv4
ports:
  - name: postgres
    protocol: TCP
    port: 5432
endpoints:
  - addresses:
      - "10.200.29.1"
    conditions:
      ready: true
```

Label kubernetes.io/service-name liên kết EndpointSlice với Service postgres cùng namespace. Port name postgres khớp với tên port trong Service. Label managed-by ghi nhận EndpointSlice do người vận hành quản lý. Địa chỉ endpoint là IP WireGuard mà PostgreSQL AWS đang lắng nghe. ready true khai báo endpoint đủ điều kiện để Service định tuyến traffic; kết nối thực tế sẽ được kiểm tra bằng client ở bước tiếp theo.

Trong Git Bash trên laptop, tạo file Azure từ file AWS.

```bash
cp deploy/kubernetes/postgres-endpoint-aws.yaml deploy/kubernetes/postgres-endpoint-azure.yaml
```

Trong file postgres-endpoint-azure.yaml, đổi địa chỉ trong endpoints thành 10.200.29.2.

```yaml
endpoints:
  - addresses:
      - "10.200.29.2"
    conditions:
      ready: true
```

Mỗi cluster có EndpointSlice postgres-wireguard riêng. Ứng dụng trong namespace issues của AWS kết nối postgres:5432 sẽ đi đến 10.200.29.1:5432. Cùng hostname trong cluster Azure sẽ đi đến 10.200.29.2:5432.

Trong Git Bash trên laptop tại thư mục gốc repository, copy file tương ứng lên từng cloud.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"

scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/postgres-endpoint-aws.yaml \
  "ubuntu@$MCF_AWS_PUBLIC_IP:"

scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/postgres-endpoint-azure.yaml \
  "azureuser@$MCF_AZURE_PUBLIC_IP:"
```

Trong phiên SSH AWS, áp dụng EndpointSlice và kiểm tra địa chỉ endpoint.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-endpoint-aws.yaml
sudo k3s kubectl -n issues get endpointslice -l kubernetes.io/service-name=postgres
```

Trong phiên SSH Azure, áp dụng EndpointSlice và kiểm tra địa chỉ endpoint.

```bash
sudo k3s kubectl apply -f /home/azureuser/postgres-endpoint-azure.yaml
sudo k3s kubectl -n issues get endpointslice -l kubernetes.io/service-name=postgres
```

Mong đợi EndpointSlice postgres-wireguard có ADDRESSTYPE IPv4, PORTS 5432 và ENDPOINTS là 10.200.29.1 trên AWS hoặc 10.200.29.2 trên Azure. Checkpoint này xác nhận ánh xạ backend đã được lưu trong cluster. Việc phân giải DNS, định tuyến Service và đăng nhập database từ Pod ứng dụng được nghiệm thu ở bước client kế tiếp.

### 7.26. Kiểm tra kết nối database từ Pod qua Service postgres

Tạo file deploy/kubernetes/postgres-service-check.yaml trên laptop. Pod client dùng mạng Pod mặc định trong namespace issues, lấy thông tin đăng nhập từ Secret postgres-auth và kết nối qua hostname postgres. Script đọc DNS, chuẩn bị password file rồi chạy truy vấn trạng thái database.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: postgres-service-check
  namespace: issues
spec:
  restartPolicy: Never
  activeDeadlineSeconds: 120
  containers:
    - name: psql
      image: postgres:17-bookworm@sha256:665dc7b37ac52a17e298511414c21d23ffa4e6a6ef6225b3e5d59c7afb35e994
      envFrom:
        - secretRef:
            name: postgres-auth
      command: ["bash", "-ec"]
      args:
        - |
          set -eu
          getent hosts postgres
          umask 077
          printf 'postgres:5432:%s:%s:%s\n' \
            "$POSTGRES_DB" "$POSTGRES_USER" "$POSTGRES_PASSWORD" \
            > /tmp/pgpass
          export PGPASSFILE=/tmp/pgpass
          export PGCONNECT_TIMEOUT=5
          exec psql -X -w -h postgres -p 5432 \
            -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
            -v ON_ERROR_STOP=1 -P pager=off -c \
            "SELECT inet_server_addr() AS server_ip, pg_is_in_recovery() AS in_recovery, current_setting('transaction_read_only') AS read_only;"
```

getent hosts kiểm tra phân giải tên postgres trong namespace issues. Password file được tạo từ Secret với quyền 600 qua umask 077; PGPASSFILE chỉ đường dẫn cho psql. PGCONNECT_TIMEOUT giới hạn thời gian thiết lập kết nối. Pod chạy một lần và kết thúc khi truy vấn hoàn tất, với activeDeadlineSeconds 120 giới hạn tổng thời gian hoạt động của lượt kiểm tra.

Trong Git Bash trên laptop tại thư mục gốc repository, copy cùng manifest lên cả hai máy.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"

scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/postgres-service-check.yaml \
  "ubuntu@$MCF_AWS_PUBLIC_IP:"

scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/postgres-service-check.yaml \
  "azureuser@$MCF_AZURE_PUBLIC_IP:"
```

Trong phiên SSH AWS, chạy client và xem kết quả.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-service-check.yaml
sudo k3s kubectl -n issues logs -f postgres-service-check --pod-running-timeout=120s
sudo k3s kubectl -n issues get pod postgres-service-check
```

Trong phiên SSH Azure, chạy client và xem kết quả.

```bash
sudo k3s kubectl apply -f /home/azureuser/postgres-service-check.yaml
sudo k3s kubectl -n issues logs -f postgres-service-check --pod-running-timeout=120s
sudo k3s kubectl -n issues get pod postgres-service-check
```

Mong đợi getent in ra ClusterIP của Service postgres tại cluster tương ứng. Kết quả SQL phía AWS cần có server_ip 10.200.29.1, in_recovery f và read_only off. Phía Azure cần có server_ip 10.200.29.2, in_recovery t và read_only on. Pod kiểm tra kết thúc với STATUS Completed; lúc này READY 0/1 phù hợp với container đã chạy xong.

Kết quả thành công xác nhận chuỗi Pod client → DNS postgres → Service ClusterIP → EndpointSlice → PostgreSQL lắng nghe trên IP WireGuard, đồng thời kiểm tra được đăng nhập bằng Secret. Với database cùng host của cluster một node, IP WireGuard đóng vai trò địa chỉ listener nội bộ host. Kết nối WAL giữa hai host sử dụng tunnel liên cloud.

Sau khi ghi nhận kết quả, có thể dọn Pod client trong từng phiên SSH bằng lệnh sau.

```bash
sudo k3s kubectl -n issues delete pod postgres-service-check
```

Để kiểm tra lại, tạo lại Pod client từ manifest. Nếu lần chạy lỗi, đọc log và describe pod trước khi dọn để đối chiếu DNS, Secret, EndpointSlice và rule xác thực PostgreSQL.

### 7.27. Chuẩn bị cấu hình nhận diện ứng dụng cho AWS và Azure

Người thực hành đã xác nhận Pod client ở mục 7.26 kết nối qua Service thành công trên cả hai cluster, với địa chỉ server và vai trò database đúng dự kiến.

Chọn image ứng dụng từ workflow run [43090850035](https://github.com/todicode/multi-cloud-failover/actions/runs/43090850035) của commit c56fd3f30baee50fa779607dc0fb1a2133b53a9d. Đã đọc GitHub Actions API xác nhận cả ba job test, container và verify-image success. Đã đối chiếu manifest GHCR của tag commit, tính lại SHA-256 của manifest và kiểm tra config image có platform linux/amd64, user appuser cùng label revision đúng commit.

Tham chiếu image được chọn để dùng chung cho hai cluster ở bước Deployment tiếp theo.

```text
ghcr.io/todicode/multi-cloud-failover@sha256:2d7cf831e50eb1c693082dc9e4f7dbf76ded557fa512a249ba68df7995b6b10e
```

Tạo file deploy/kubernetes/app-config-aws.yaml trên laptop với nội dung sau.

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: issues-app-config
  namespace: issues
data:
  APP_ENV: "aws"
  APP_REGION: "ap-southeast-1"
  APP_VERSION: "v0.1.0"
  COMMIT_SHA: "c56fd3f30baee50fa779607dc0fb1a2133b53a9d"
```

Ứng dụng đọc các biến này khi process khởi động. APP_ENV xác định môi trường phục vụ request và được ghi vào header X-Served-By. APP_REGION, APP_VERSION và COMMIT_SHA được trả về qua endpoint /version. COMMIT_SHA khớp revision của image đã chọn. Khi chọn image từ bản build mới, đối chiếu lại revision và cập nhật cấu hình tương ứng trước rollout.

Trong Git Bash trên laptop, tạo cấu hình Azure từ file AWS.

```bash
cp deploy/kubernetes/app-config-aws.yaml deploy/kubernetes/app-config-azure.yaml
```

Trong file app-config-azure.yaml, đặt APP_ENV thành azure và APP_REGION thành southeastasia. Phần data cần có nội dung sau.

```yaml
data:
  APP_ENV: "azure"
  APP_REGION: "southeastasia"
  APP_VERSION: "v0.1.0"
  COMMIT_SHA: "c56fd3f30baee50fa779607dc0fb1a2133b53a9d"
```

Mỗi cluster có ConfigMap issues-app-config riêng. Thông tin đăng nhập database đã có trong Secret postgres-auth. Deployment sẽ tham chiếu ConfigMap và Secret khi cấu hình môi trường container.

Trong Git Bash trên laptop tại thư mục gốc repository, copy file tương ứng lên từng máy.

```bash
MCF_AWS_PUBLIC_IP="$(terraform -chdir=deploy/terraform/aws output -raw aws_public_ip)"
MCF_AZURE_PUBLIC_IP="$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)"

scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/app-config-aws.yaml \
  "ubuntu@$MCF_AWS_PUBLIC_IP:"

scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/app-config-azure.yaml \
  "azureuser@$MCF_AZURE_PUBLIC_IP:"
```

Trong phiên SSH AWS, áp dụng và kiểm tra ConfigMap.

```bash
sudo k3s kubectl apply -f /home/ubuntu/app-config-aws.yaml
sudo k3s kubectl -n issues get configmap issues-app-config
```

Trong phiên SSH Azure, áp dụng và kiểm tra ConfigMap.

```bash
sudo k3s kubectl apply -f /home/azureuser/app-config-azure.yaml
sudo k3s kubectl -n issues get configmap issues-app-config
```

Mong đợi ConfigMap issues-app-config có DATA bằng 4 trên mỗi cluster. Checkpoint này xác nhận cấu hình runtime đã được lưu để Deployment sử dụng ở bước tiếp theo.

## 8. Tạm nghỉ và giữ môi trường lab

### 8.1. Dừng compute trên hai cloud

Ở trạng thái thực hành hiện tại, cấu hình K3s, WireGuard, Secret và tài nguyên Kubernetes được lưu trên ổ hệ điều hành của từng máy. Khi tạm nghỉ, dừng EC2 và deallocate VM Azure để giữ môi trường đã cấu hình cho buổi tiếp theo.

Mở tab Git Bash trên laptop tại thư mục gốc repository. Lấy instance ID AWS hiện tại rồi dừng máy bằng API cloud.

```bash
MCF_AWS_INSTANCE_ID="$(terraform -chdir=deploy/terraform/aws output -raw aws_instance_id)"

aws ec2 stop-instances \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids "$MCF_AWS_INSTANCE_ID" \
  --no-cli-pager

aws ec2 wait instance-stopped \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids "$MCF_AWS_INSTANCE_ID"
```

Lệnh stop gửi yêu cầu tắt máy, còn wait đợi trạng thái `stopped`. Sau đó deallocate đúng VM Azure trong subscription project.

```bash
az vm deallocate \
  --resource-group mcf-azure-rg \
  --name mcf-azure-standby
```

Kiểm tra trạng thái sau khi các thao tác hoàn tất.

```bash
aws ec2 describe-instances \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids "$MCF_AWS_INSTANCE_ID" \
  --query 'Reservations[].Instances[].State.Name' \
  --output text \
  --no-cli-pager

az vm show \
  --resource-group mcf-azure-rg \
  --name mcf-azure-standby \
  --show-details \
  --query powerState \
  --output tsv
```

Mong đợi AWS `stopped` và Azure `VM deallocated`. Trên Azure Portal, trạng thái tương ứng là `Stopped (deallocated)`. Phí sử dụng compute dừng theo trạng thái này. Azure `Stopped (Allocated)` vẫn tính phí compute, vì vậy cần kiểm tra đúng trạng thái deallocated.

Các tài nguyên lưu giữ tiếp tục được tính phí, gồm AWS EBS và Elastic IP, Azure managed OS disk và Static Public IP. Việc giữ chúng bảo toàn môi trường đang thực hành qua lần tạm nghỉ. Theo dõi chi phí thực tế trong tài khoản cloud.

Đã thực hiện tạm dừng theo yêu cầu người thực hành ngày 2026-11-11. Trước thao tác, đối chiếu đúng instance/VM, tên và tag Project. Sau thao tác, AWS API xác nhận EC2 `mcf-aws-primary` ở trạng thái `stopped`, giữ root EBS và Elastic IP. Azure API xác nhận VM `mcf-azure-standby` ở trạng thái `VM deallocated`, giữ OS disk `mcf-azure-osdisk` và Static Public IP.

Buổi tiếp theo khởi động lại hai máy bằng cloud CLI hoặc Portal, kiểm tra trạng thái, rồi xác nhận K3s và WireGuard hoạt động trước khi tiếp tục phần database. Điểm tiếp tục hiện tại là kiểm tra ConfigMap sau bước 7.7, rồi chuẩn bị các tài nguyên triển khai PostgreSQL.

### 8.2. Bật lại hai máy và tiếp tục thực hành

Trong Git Bash trên laptop đã chọn đúng subscription Azure, lấy instance ID hiện tại và bật hai máy.

```bash
MCF_AWS_INSTANCE_ID="$(terraform -chdir=deploy/terraform/aws output -raw aws_instance_id)"

aws ec2 start-instances \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids "$MCF_AWS_INSTANCE_ID" \
  --no-cli-pager

az vm start \
  --resource-group mcf-azure-rg \
  --name mcf-azure-standby
```

Kiểm tra EC2 status bằng lệnh ở mục 3.5 và trạng thái Azure bằng lệnh ở mục 5.3. Đối chiếu Public IP từ Terraform outputs với trạng thái máy trước khi kết nối SSH.

Đã thực hiện bật lại theo yêu cầu người thực hành ngày 2026-11-12. AWS API xác nhận EC2 running với System và Instance status đều ok. Azure API xác nhận VM running và provisioning Succeeded. Hai Public IP tiếp tục được cấp cho đúng máy tại thời điểm kiểm tra.

Phiên kiểm tra SSH tự động gặp bước mở khóa private key có passphrase. Người thực hành sử dụng terminal tương tác để mở khóa key khi đăng nhập, rồi kiểm tra service trên mỗi máy.

```bash
sudo systemctl is-active k3s wg-quick@wg0
sudo k3s kubectl get nodes
```

Mong đợi hai dòng active và node Ready. Kiểm tra lại ping theo mục 6.11. Trên AWS, đọc ConfigMap tại điểm tiếp tục của phần PostgreSQL.

```bash
sudo k3s kubectl -n issues get configmap postgres-config
```

ConfigMap sau bước 7.7 cần có DATA bằng 2. Người thực hành đã cung cấp kết quả AWS có service K3s và WireGuard active, node mcf-aws-primary Ready và ConfigMap postgres-config có DATA bằng 2 sau lần bật lại ngày 2026-11-12. Các kiểm tra sau khởi động trên Azure và ping tunnel được xác nhận theo kết quả thực hành tương ứng.

## 9. Theo dõi tiến độ

- [x] Bắt đầu tài liệu giai đoạn 5 và thống nhất hai cluster K3s độc lập.
- [x] Đối chiếu một lượt tạo lại AWS và dọn lab theo yêu cầu; đã xóa root EBS và xác nhận state trống theo mục 3.4.
- [x] Tạo lại AWS và đọc đủ ba Terraform output theo kết quả người thực hành cung cấp.
- [x] Nghiệm thu EC2 status checks và SSH vào Ubuntu theo xác nhận của người thực hành.
- [x] Kiểm tra CPU, RAM, disk, swap và UFW theo kết quả người thực hành cung cấp.
- [ ] Xác nhận cloud-init hoàn tất và hai gói curl/ca-certificates đã được chuẩn bị.
- [x] Tạo và kiểm tra file cấu hình K3s trên AWS theo kết quả người thực hành cung cấp.
- [x] Cài K3s v1.35.1+k3s1 trên AWS, xác nhận service active và phiên bản theo kết quả người thực hành cung cấp.
- [x] Kiểm tra node Ready, các Pod hệ thống và StorageClass trên AWS theo kết quả người thực hành cung cấp.
- [x] Lập và đối chiếu plan tạo lại Azure theo xác nhận của người thực hành.
- [x] Đọc đủ ba Terraform output của lượt triển khai Azure mới theo kết quả người thực hành cung cấp.
- [x] Tạo lại Azure, kiểm tra trạng thái VM và nghiệm thu SSH theo xác nhận của người thực hành.
- [x] Kiểm tra CPU, RAM, disk, swap và UFW trên Azure theo kết quả người thực hành cung cấp.
- [ ] Xác nhận cloud-init hoàn tất và công cụ curl/ca-certificates đã được chuẩn bị trên Azure.
- [x] Tạo và kiểm tra file cấu hình K3s trên Azure theo xác nhận của người thực hành.
- [x] Cài K3s v1.35.1+k3s1 trên Azure và kiểm tra service, phiên bản theo xác nhận của người thực hành.
- [x] Nghiệm thu node Ready, các Pod hệ thống và StorageClass trên Azure theo xác nhận của người thực hành.
- [x] Cài công cụ WireGuard trên AWS và Azure theo xác nhận của người thực hành.
- [x] Tạo và ghi lại public key WireGuard riêng của AWS và Azure theo kết quả người thực hành cung cấp.
- [x] Khai báo, đối chiếu plan và apply rule WireGuard phía AWS, đã có resource trong state local.
- [x] Khai báo, đối chiếu plan và apply rule WireGuard phía Azure, đã có resource trong state local với source, protocol và port đúng dự kiến.
- [x] Đối chiếu public key, quyền file key và route hiện tại trên cả hai máy.
- [x] Tạo và kiểm tra file wg0.conf phía AWS, quyền 600 root:root theo kết quả người thực hành cung cấp.
- [x] Tạo và kiểm tra file wg0.conf phía Azure, quyền 600 root:root theo kết quả người thực hành cung cấp.
- [x] Bật WireGuard và kiểm tra handshake, route, ping hai chiều theo output người thực hành cung cấp.
- [x] Cấu hình WireGuard giữa hai máy và nghiệm thu kết nối tunnel.
- [x] Tạo manifest namespace issues trong repository và sử dụng namespace trên AWS, đã tạo PVC thành công trong namespace này.
- [x] Áp dụng cùng manifest namespace issues trên Azure theo output người thực hành cung cấp.
- [x] Tạo StorageClass local-path-retain trên AWS, PV đã cấp có policy Retain theo output người thực hành cung cấp.
- [x] Tạo PVC postgres-data trên AWS, Pending với event Normal WaitForFirstConsumer theo output người thực hành cung cấp.
- [x] Tạo Secret postgres-auth trên AWS, Opaque và đủ ba key có kích thước đúng theo output người thực hành cung cấp.
- [x] Tạo manifest ConfigMap AWS có postgresql.conf và pg_hba.conf, ConfigMap trên cluster có DATA bằng 2 theo output người thực hành cung cấp.
- [x] Tạo manifest headless Service postgres-headless và áp dụng trên AWS theo xác nhận của người thực hành.
- [x] Triển khai StatefulSet PostgreSQL AWS, Pod 1/1 Running và PVC Bound theo output người thực hành cung cấp.
- [x] Xác nhận PostgreSQL AWS primary, read_only off, cấu hình hiệu lực đúng và PV Retain theo output người thực hành cung cấp.
- [x] Áp dụng schema SQL lên AWS, đủ sáu bảng và app_control có writes_enabled t theo output người thực hành cung cấp.
- [x] Tạo role replicator trên AWS, LOGIN và REPLICATION đều t theo output người thực hành cung cấp.
- [x] Gán mật khẩu replication và kiểm tra SCRAM, scram_password t theo output người thực hành cung cấp.
- [x] Áp dụng namespace, StorageClass Retain và PVC PostgreSQL trên Azure trước khi clone standby theo output người thực hành cung cấp.
- [ ] Tạo Secret postgres-replication trên Azure, kiểm tra đủ hai key và kích thước dự kiến.
- [x] Tạo và áp dụng ConfigMap PostgreSQL Azure, DATA bằng 2 với listen_addresses chứa IP WireGuard Azure theo manifest local và output người thực hành cung cấp.
- [ ] Áp dụng headless Service postgres-headless trên Azure và kiểm tra CLUSTER-IP None, port 5432/TCP.
- [ ] Tạo Secret postgres-auth trên Azure với thông tin từ AWS, kiểm tra đủ ba key và kích thước dự kiến.
- [ ] Tạo ConfigMap postgres-clone-script trên Azure, DATA bằng 1 để chuẩn bị Job clone.
- [x] Chạy Job postgres-clone trên Azure, Job Complete 1/1 trong 27 giây và PVC Bound theo output người thực hành cung cấp.
- [x] Triển khai StatefulSet PostgreSQL Azure, Pod Running 1/1, in_recovery t và read_only on theo output người thực hành cung cấp.
- [x] Xác nhận WAL sender AWS và WAL receiver Azure đều streaming qua đúng IP WireGuard, chế độ async theo xác nhận của người thực hành.
- [x] Triển khai PostgreSQL primary/standby và kiểm tra WAL streaming theo kết quả vai trò database và xác nhận của người thực hành.
- [x] Ghi bản ghi probe_pings mới trên AWS và đọc lại trên Azure với run_id tương ứng, seq 1 và environment aws theo kết quả người thực hành cung cấp.
- [x] Tạo Service postgres trên AWS và Azure để chuẩn bị kết nối database từ ứng dụng theo xác nhận của người thực hành.
- [x] Áp dụng EndpointSlice postgres-wireguard ở mỗi cluster, xác nhận đúng endpoint IP WireGuard và port 5432 theo xác nhận của người thực hành.
- [x] Chạy Pod client ở cả hai cluster, kiểm tra DNS postgres, đăng nhập qua Service và vai trò database đúng từng cloud theo xác nhận của người thực hành.
- [x] Chọn image ứng dụng từ CI run 43090850035 đã thành công, đối chiếu GHCR manifest digest, platform, user và revision.
- [ ] Tạo ConfigMap issues-app-config trên AWS và Azure với bốn key nhận diện môi trường, region, version và commit.
- [ ] Triển khai ứng dụng bằng cùng image digest trên hai cluster.
- [ ] Kiểm tra endpoint, vai trò database và dữ liệu nghiệp vụ đã replay.

## 10. Tài liệu kỹ thuật

- [K3s Quick-Start: single-node server và các thành phần đi kèm](https://docs.k3s.io/quick-start).
- [K3s requirements](https://docs.k3s.io/installation/requirements).
- [K3s configuration options](https://docs.k3s.io/installation/configuration).
- [K3s v1.35.1+k3s1 release](https://github.com/k3s-io/k3s/releases/tag/v1.35.1%2Bk3s1).
- [Terraform saved plan apply](https://developer.hashicorp.com/terraform/cli/commands/apply#saved-plan-mode).
- [AWS EC2 SSH connection prerequisites](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-to-linux-instance.html).
- [Azure VM show](https://learn.microsoft.com/en-us/cli/azure/vm#az-vm-show).
- [Azure Linux VM Run Command](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/run-command).
- [WireGuard installation](https://www.wireguard.com/install/).
- [WireGuard quick start](https://www.wireguard.com/quickstart/).
- [wg-quick configuration reference](https://git.zx2c4.com/wireguard-tools/about/src/man/wg-quick.8).
- [WireGuard systemd unit](https://git.zx2c4.com/wireguard-tools/tree/src/systemd/wg-quick@.service).
- [wg runtime status reference](https://git.zx2c4.com/wireguard-tools/about/src/man/wg.8).
- [Kubernetes namespaces](https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/).
- [Kubernetes StorageClasses](https://kubernetes.io/docs/concepts/storage/storage-classes/).
- [Kubernetes PersistentVolumeClaims](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#persistentvolumeclaims).
- [Kubernetes Secrets with kubectl](https://kubernetes.io/docs/tasks/configmap-secret/managing-secret-using-kubectl/).
- [Kubernetes StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/).
- [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/).
- [Kubernetes headless Services](https://kubernetes.io/docs/concepts/services-networking/service/#headless-services).
- [Kubernetes Services and manually managed EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/service/#services-without-selectors).
- [Kubernetes EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).
- [PostgreSQL 17 replication parameters](https://www.postgresql.org/docs/17/runtime-config-replication.html).
- [PostgreSQL 17 connection parameters](https://www.postgresql.org/docs/17/runtime-config-connection.html).
- [PostgreSQL 17 pg_hba.conf](https://www.postgresql.org/docs/17/auth-pg-hba-conf.html).
- [PostgreSQL official container image](https://hub.docker.com/_/postgres).
- [PostgreSQL official image entrypoint](https://github.com/docker-library/postgres/blob/master/docker-entrypoint.sh).
- [PostgreSQL 17 pg_isready](https://www.postgresql.org/docs/17/app-pg-isready.html).
- [PostgreSQL 17 administration and recovery functions](https://www.postgresql.org/docs/17/functions-admin.html).
- [PostgreSQL 17 transaction defaults](https://www.postgresql.org/docs/17/runtime-config-client.html).
- [PostgreSQL 17 psql scripting](https://www.postgresql.org/docs/17/app-psql.html).
- [PostgreSQL 17 CREATE ROLE](https://www.postgresql.org/docs/17/sql-createrole.html).
- [PostgreSQL 17 ALTER ROLE](https://www.postgresql.org/docs/17/sql-alterrole.html).
- [PostgreSQL 17 streaming replication](https://www.postgresql.org/docs/17/warm-standby.html#STREAMING-REPLICATION).
- [PostgreSQL 17 pg_basebackup](https://www.postgresql.org/docs/17/app-pgbasebackup.html).
- [PostgreSQL 17 password file](https://www.postgresql.org/docs/17/libpq-pgpass.html).
- [PostgreSQL 17 replication monitoring views](https://www.postgresql.org/docs/17/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW).
- [PostgreSQL 17 UUID functions](https://www.postgresql.org/docs/17/functions-uuid.html).
- [AWS EC2 stop and start](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Stop_Start.html).
- [AWS EC2 instance states and billing](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html).
- [Azure VM states and billing](https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing).
- [Azure Public IP pricing](https://azure.microsoft.com/en-us/pricing/details/ip-addresses/).
- [Local Path Provisioner](https://github.com/rancher/local-path-provisioner).
- [AWS provider v6.72.0 security group ingress rule](https://github.com/hashicorp/terraform-provider-aws/blob/v6.72.0/website/docs/r/vpc_security_group_ingress_rule.html.markdown).
- [AzureRM provider v4.81.0 network security rule](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/network_security_rule.html.markdown).
