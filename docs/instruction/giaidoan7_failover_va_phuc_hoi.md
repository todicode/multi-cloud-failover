# Giai đoạn 7 — Failover và phục hồi

## 1. Mục tiêu và đầu ra

Thực hành chuyển writer và truy cập ứng dụng từ AWS sang Azure, đưa AWS trở lại làm standby, rồi failback có kiểm soát về AWS. Luồng vận hành phải duy trì một PostgreSQL writer tại mỗi thời điểm và có bằng chứng kiểm tra dữ liệu sau chuyển đổi.

Giai đoạn này phục vụ các yêu cầu S2 về chuyển traffic, S3 về mất khả dụng một môi trường và S5 về độ phức tạp vận hành. Mỗi bước thực hành ghi rõ nơi chạy, lý do, lệnh, kết quả mong đợi và điều kiện tiếp tục.

## 2. Trạng thái bắt đầu

- Giai đoạn 6 đã nghiệm thu DNS, HTTPS, writer health checks và renewal dry-run kèm deploy hook trên hai cloud.
- PostgreSQL AWS giữ vai trò primary, Azure giữ vai trò standby trong lượt nghiệm thu gần nhất.
- Hai ứng dụng dùng image ghcr.io/todicode/multi-cloud-failover@sha256:2d7cf831e50eb1c693082dc9e4f7dbf76ded557fa512a249ba68df7995b6b10e, ứng với commit c56fd3f30baee50fa779607dc0fb1a2133b53a9d.
- Hai máy đã được dừng để tiết kiệm chi phí. Lần xác nhận gần nhất ghi nhận EC2 Stopped và Azure VM Deallocated.
- Manifest PostgreSQL AWS hiện khởi động database từ PVC hiện có. Cơ chế kiểm soát writer cũ khi máy khởi động lại cần được bổ sung và kiểm tra trước bài thử failover.

| Thành phần | Giá trị của lab hiện tại |
|---|---|
| AWS profile và account | default, 925271162060 |
| AWS region | ap-southeast-1 |
| EC2 | i-014ee6f4d204aacb7, mcf-aws-primary |
| AWS public IP và WireGuard IP | 175.41.152.242, 10.200.29.1 |
| Azure subscription | 52341a4a-a86f-4780-82dc-879b500022d8 |
| Azure resource group và VM | mcf-azure-rg, mcf-azure-standby |
| Azure public IP và WireGuard IP | 4.145.30.250, 10.200.29.2 |
| Hostname chung | app.mcf.todicode.tech |
| Namespace và workload | issues, StatefulSet postgres, Deployment issues-app |

Các định danh trên thuộc lượt triển khai hiện tại. Người tái dựng dùng account cùng Terraform output của lần triển khai của mình để chọn tài nguyên.

## 3. Trình tự thực hành

1. Đối chiếu danh tính cloud và tài nguyên sẽ vận hành.
2. Khởi động lab và kiểm tra lại kết nối, vai trò database cùng WAL streaming.
3. Chuẩn bị cơ chế kiểm soát writer cũ khi khởi động lại.
4. Thực hành mất khả dụng AWS, xác nhận fencing rồi promote Azure.
5. Kiểm tra writer, truy cập qua hostname chung và dữ liệu sau failover.
6. Rejoin AWS thành standby của Azure bằng dữ liệu đồng bộ từ writer hiện tại.
7. Failback có kiểm soát về AWS và đưa Azure trở lại standby.

PostgreSQL lưu vai trò cùng dữ liệu trên disk. Sau khi promote Azure, AWS cũ cần được đưa trở lại theo vai trò và dữ liệu phù hợp để duy trì một writer. DNS chọn đích truy cập dựa trên health check. Việc kiểm soát writer được thực hiện ở luồng fencing và phục hồi database. [PostgreSQL failover](https://www.postgresql.org/docs/17/warm-standby-failover.html).

## 4. Thực hành từng bước

### 4.1. Xác nhận AWS account và EC2 trước khi vận hành

Chạy trong Git Bash trên laptop tại thư mục gốc repository. Bước này sử dụng các API đọc thông tin để xác nhận account và instance. Danh tính đúng cùng instance ID cụ thể là cơ sở cho các bước start, fencing và phục hồi sau đó.

```bash
aws sts get-caller-identity \
  --profile default \
  --query '{Account:Account,Arn:Arn}' \
  --output table \
  --no-cli-pager
```

- sts get-caller-identity trả danh tính của credential AWS CLI đang sử dụng.
- profile default chọn profile đã quản lý tài nguyên của project.
- query chọn hai trường Account và Arn để đối chiếu account cùng IAM principal.
- output table hiển thị kết quả thành bảng. no-cli-pager đưa output trực tiếp về terminal.

Trong lab hiện tại, Account mong đợi là 925271162060, Arn là arn:aws:iam::925271162060:user/todicode.

Tiếp theo kiểm tra EC2 cụ thể.

```bash
aws ec2 describe-instances \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids i-014ee6f4d204aacb7 \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name}' \
  --output table \
  --no-cli-pager
```

- region chọn Singapore, nơi EC2 của project đã được tạo.
- instance-ids giới hạn request vào instance sẽ được sử dụng trong bài thực hành.
- Reservations[].Instances[] truy cập danh sách instance trong response của EC2 API.
- Phần query chọn InstanceId và State.Name để bảng kết quả chứa hai cột Id và State.

Mong đợi Id là i-014ee6f4d204aacb7 và State là stopped sau lần nghỉ lab. Khi đối chiếu được account và instance, bước tiếp theo xác nhận VM Azure rồi khởi động lab để chuẩn bị kiểm tra lại replication.

Các thông tin này đã được đối chiếu trong lần dừng lab ngay trước giai đoạn 7. AWS account là 925271162060, EC2 i-014ee6f4d204aacb7 đã Stopped. Azure subscription 52341a4a-a86f-4780-82dc-879b500022d8 chứa VM mcf-azure-standby trong resource group mcf-azure-rg, đã xác nhận Deallocated. Các lệnh ở mục 4.1 dùng để đối chiếu khi thay đổi profile, account hoặc lượt triển khai.

### 4.2. Khởi động AWS để chuẩn bị topology ban đầu

Lượt thực hành bắt đầu từ AWS primary và Azure standby đã nghiệm thu ở giai đoạn 6. Khởi động AWS trước để PostgreSQL primary sẵn sàng phục vụ và gửi WAL khi Azure được bật ở bước tiếp theo. EC2 bắt đầu phát sinh phí compute khi hoạt động trở lại.

Trong Git Bash trên laptop, chạy lệnh sau.

```bash
aws ec2 start-instances \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids i-014ee6f4d204aacb7 \
  --no-cli-pager
```

start-instances yêu cầu AWS khởi động EC2 hiện có. profile, region và instance-ids chọn đúng account, region và máy đã đối chiếu ở mục 4.1. no-cli-pager hiển thị response trực tiếp trong terminal. Response thường cho thấy PreviousState stopped và CurrentState pending.

Tiếp theo chờ EC2 vượt qua status checks.

```bash
aws ec2 wait instance-status-ok \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids i-014ee6f4d204aacb7
```

wait instance-status-ok là waiter của AWS CLI, tự truy vấn định kỳ và kết thúc thành công khi instance chạy và các kiểm tra trạng thái đạt. Lệnh thường mất vài phút và trả về prompt với exit code 0 khi thành công. Status checks kiểm tra tình trạng hạ tầng và instance. K3s, PostgreSQL, WireGuard cùng vai trò database được kiểm tra riêng sau khi hai máy được bật.

Checkpoint này hoàn tất khi start được chấp nhận và waiter thành công. Bước tiếp theo khởi động Azure, sau đó kiểm tra trạng thái workload và replication trước khi thay đổi cơ chế điều khiển writer.

### 4.3. Khởi động Azure

Trong lượt thực hành này, EC2 AWS đã ở trạng thái running khi kiểm tra và cả SystemStatus, InstanceStatus đều ok. Người vận hành yêu cầu khởi động hai cloud để tiếp tục. Đã gửi lệnh start cho VM Azure đang Deallocated.

Lệnh tham chiếu để khởi động Azure từ Git Bash trên laptop.

```bash
az vm start \
  --subscription 52341a4a-a86f-4780-82dc-879b500022d8 \
  --resource-group mcf-azure-rg \
  --name mcf-azure-standby
```

subscription chọn gói Azure for Students của lượt triển khai. resource-group và name xác định VM của project. start cấp lại compute cho VM từ các tài nguyên disk và NIC đã giữ lại, cho phép Ubuntu cùng các dịch vụ tự khởi động. Sau khi bật Azure, bước tiếp theo kiểm tra dịch vụ và workload trên hai máy.

Đã đối chiếu Azure API trả PowerState/running và ProvisioningState/succeeded sau lệnh start.

### 4.4. Kiểm tra dịch vụ và Kubernetes trên AWS sau khi bật máy

Mở terminal SSH tới AWS từ Git Bash trên laptop.

```bash
ssh -i ~/.ssh/mcf-lab ubuntu@175.41.152.242
```

Trong terminal Ubuntu của AWS, chạy các lệnh sau.

```bash
sudo systemctl is-active k3s wg-quick@wg0
sudo k3s kubectl get nodes
sudo k3s kubectl -n issues get pods -o wide
```

systemctl is-active kiểm tra hai dịch vụ của host. k3s vận hành Kubernetes của cloud này, wg-quick@wg0 vận hành WireGuard interface dùng cho WAL giữa hai cloud. Mong đợi hai dòng active.

kubectl get nodes kiểm tra Kubernetes đã nhận node mcf-aws-primary ở trạng thái Ready. EC2 status checks xác nhận tình trạng hạ tầng và instance, còn node Ready xác nhận lớp Kubernetes đã sẵn sàng.

kubectl -n issues get pods -o wide tập trung vào workload của project, hiển thị trạng thái container, restart count, IP và node. Mong đợi postgres-0 cùng Pod issues-app đạt 1/1 Running sau khi khởi động ổn định. Các kết quả này chuẩn bị cho bước truy vấn vai trò database và kiểm tra replication.

Checkpoint hiện tại là đối chiếu hai dịch vụ active, node Ready và hai workload Running trên AWS. Bước tiếp theo kiểm tra tương ứng trên Azure rồi đối chiếu primary/standby và WAL streaming.

Kết quả thực hành trên AWS đã xác nhận issues-app-f8fb495f5-thvkw và postgres-0 đều 1/1 Running. App Pod có IP 10.42.0.31 trong mạng Pod, PostgreSQL có IP host 10.29.1.8 do cấu hình hostNetwork. Pod postgres-service-check đã Completed sau lượt kiểm tra kết nối ở giai đoạn trước, phù hợp restartPolicy Never trong manifest của Pod kiểm tra.

### 4.5. Kiểm tra dịch vụ và Kubernetes trên Azure sau khi bật máy

Hai cluster có control plane và workload độc lập. Kiểm tra Azure để xác nhận môi trường standby phục hồi sau lần nghỉ, trước khi đối chiếu replication với AWS.

Trong một terminal Git Bash khác trên laptop, mở SSH tới Azure.

```bash
ssh -i ~/.ssh/mcf-lab azureuser@4.145.30.250
```

Trong terminal Ubuntu của Azure, chạy lần lượt các lệnh sau.

```bash
sudo systemctl is-active k3s wg-quick@wg0
sudo k3s kubectl get nodes
sudo k3s kubectl -n issues get pods -o wide
```

Mong đợi hai dịch vụ active, node mcf-azure-standby Ready và các Pod postgres-0 cùng issues-app đạt 1/1 Running. systemctl kiểm tra dịch vụ host, get nodes kiểm tra node trong cluster Azure và get pods kiểm tra workload của namespace issues. Lệnh kubectl chạy qua k3s trên VM hiện tại sử dụng cluster của VM đó.

Pod postgres-clone có thể hiện Completed vì tác vụ clone ban đầu đã kết thúc. Các workload phục vụ ứng dụng và database cần đạt trạng thái Running. PostgreSQL trên Azure dùng hostNetwork nên IP Pod là địa chỉ private của VM, còn App Pod dùng mạng Pod của K3s.

Checkpoint này hoàn tất khi đối chiếu dịch vụ, node và hai workload phục vụ trên Azure. Bước tiếp theo truy vấn vai trò PostgreSQL và trạng thái WAL để xác nhận topology AWS primary, Azure standby sau khi bật lại.

Kết quả thực hành trên Azure đã xác nhận issues-app-f8fb495f5-lf458 và postgres-0 đều 1/1 Running. PostgreSQL dùng IP host 10.30.1.4, App Pod dùng IP 10.42.0.31. Pod clone cùng Pod kiểm tra kết nối đã Completed.

### 4.6. Xác nhận vai trò PostgreSQL trên hai cloud

Sau khi đối chiếu Pod của cả hai cloud đang Running và Ready, truy vấn PostgreSQL để xác định vai trò cùng chế độ transaction hiện tại. Việc này tạo checkpoint topology trước khi kiểm tra replication và thực hành chuyển writer.

Chạy cùng lệnh sau một lần trong terminal SSH Ubuntu của AWS và một lần trong terminal SSH Ubuntu của Azure.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT pg_is_in_recovery() AS in_recovery,
          current_setting('transaction_read_only') AS read_only;"
```

- kubectl -n issues exec postgres-0 chạy lệnh trong container PostgreSQL của Pod postgres-0 thuộc cluster đang được truy cập trên VM hiện tại.
- Dấu -- phân tách tham số kubectl với lệnh psql được chạy trong container.
- psql là PostgreSQL client có sẵn trong image database.
- -X bỏ qua file tùy chỉnh khởi động psql để truy vấn thực hành dùng cấu hình lệnh đã chỉ định.
- -U taskflow chọn database user, -d taskflow chọn database.
- -P pager=off in toàn bộ kết quả trực tiếp trong terminal.
- -c thực thi câu SQL được truyền vào, rồi psql kết thúc.
- pg_is_in_recovery() trả true khi PostgreSQL đang recovery. Standby vật lý của project chạy ở chế độ này để replay WAL từ primary.
- current_setting('transaction_read_only') trả trạng thái read-only của transaction đang chạy truy vấn. AS đặt tên cột kết quả.

Kết quả mong đợi.

| Cloud | in_recovery | read_only | Diễn giải trong topology của lab |
|---|---|---|---|
| AWS | f | off | Primary, transaction kiểm tra có chế độ read-write |
| Azure | t | on | Standby đang recovery, transaction read-only |

psql hiển thị boolean false bằng f và true bằng t. Các giá trị recovery và read-only mô tả trạng thái database tại thời điểm truy vấn. Trạng thái kết nối streaming và dữ liệu đã replay được đối chiếu ở checkpoint WAL tiếp theo. [PostgreSQL recovery functions](https://www.postgresql.org/docs/17/functions-admin.html#FUNCTIONS-RECOVERY-INFO-TABLE), [transaction_read_only](https://www.postgresql.org/docs/17/runtime-config-client.html#GUC-TRANSACTION-READ-ONLY).

Checkpoint này hoàn tất khi AWS trả f/off và Azure trả t/on. Bước tiếp theo kiểm tra WAL sender trên AWS và receiver trên Azure để xác nhận replication đã kết nối lại sau lần nghỉ.

Đã xác nhận AWS trả in_recovery f và read_only off, Azure trả in_recovery t và read_only on sau khi bật lab.

### 4.7. Kiểm tra hai đầu WAL streaming

Vai trò database đã đúng. Kiểm tra WAL sender trên AWS và WAL receiver trên Azure để xác nhận kết nối replication đang hoạt động. Standby có thể tiếp tục chạy recovery với dữ liệu đã nhận trong khi kết nối tới primary bị gián đoạn, nên trạng thái recovery cần được đối chiếu cùng trạng thái streaming.

Trong terminal SSH Ubuntu của AWS, chạy lệnh sau.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT client_addr, state, sync_state,
          sent_lsn, write_lsn, flush_lsn, replay_lsn
   FROM pg_stat_replication;"
```

pg_stat_replication là system view cung cấp thông tin các WAL sender. Với topology hiện tại, mong đợi một dòng với client_addr 10.200.29.2, state streaming và sync_state async. client_addr là IP WireGuard của standby Azure mà AWS quan sát được. streaming biểu thị sender đang phục vụ luồng WAL, async là chế độ replication bất đồng bộ.

sent_lsn là vị trí WAL đã gửi. write_lsn, flush_lsn và replay_lsn là các vị trí standby đã báo lại, lần lượt thể hiện WAL đã ghi, đã flush tới disk và đã replay. LSN là vị trí trong luồng WAL, được hiển thị theo dạng hexadecimal. Các cột này giúp đối chiếu tiến độ truyền và áp dụng dữ liệu.

Trong terminal SSH Ubuntu của Azure, chạy lệnh sau.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT status, sender_host, sender_port,
          pg_last_wal_receive_lsn() AS receive_lsn,
          pg_last_wal_replay_lsn() AS replay_lsn
   FROM pg_stat_wal_receiver;"
```

pg_stat_wal_receiver là system view của WAL receiver trên standby. Mong đợi một dòng với status streaming, sender_host 10.200.29.1 và sender_port 5432. Hai hàm lấy vị trí WAL đã nhận và đồng bộ xuống disk qua streaming, cùng vị trí đã replay trên Azure.

Các tùy chọn kubectl exec và psql dùng như mục 4.6. Phần SQL thay đổi để quan sát hai đầu của kết nối replication. Hai truy vấn diễn ra tại các thời điểm khác nhau, nên đối chiếu LSN theo trạng thái tải hiện tại. Khi tải ghi ổn định và standby bắt kịp, receive_lsn và replay_lsn thường bằng nhau. [PostgreSQL replication statistics](https://www.postgresql.org/docs/17/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW), [WAL receiver statistics](https://www.postgresql.org/docs/17/monitoring-stats.html#MONITORING-PG-STAT-WAL-RECEIVER-VIEW).

Checkpoint này hoàn tất khi AWS và Azure đều có dòng streaming với địa chỉ peer đúng. Bước tiếp theo ghi một bản ghi kiểm chứng mới trên AWS và xác nhận bản ghi được replay trên Azure trước khi thực hành failover.

Kết quả thực hành đã xác nhận AWS có một WAL sender tới 10.200.29.2 ở trạng thái streaming, sync_state async. sent_lsn, write_lsn, flush_lsn và replay_lsn đều là 0/3006C20. Azure có WAL receiver từ 10.200.29.1:5432 ở trạng thái streaming, receive_lsn và replay_lsn đều là 0/3006C20 tại thời điểm đối chiếu.

### 4.8. Ghi bản ghi kiểm chứng mới trên AWS

Streaming cùng các vị trí LSN đã được đối chiếu. Ghi thêm dữ liệu mới để kiểm chứng PostgreSQL Azure replay được một transaction phát sinh sau lần bật máy. Bảng probe_pings đã có trong schema ứng dụng và được thiết kế để lưu các bản ghi kiểm chứng.

Trong terminal SSH Ubuntu của AWS, chạy lệnh sau.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "INSERT INTO probe_pings (run_id, seq, environment)
   VALUES ('stage7-preflight-' || gen_random_uuid()::text, 1, 'aws')
   RETURNING run_id, seq, environment, created_at;"
```

Các tham số kubectl và psql giống mục 4.6. INSERT INTO chọn bảng và ba cột được gán giá trị. gen_random_uuid() tạo mã UUID cho lượt kiểm chứng. ::text chuyển UUID sang text, còn toán tử || nối chuỗi stage7-preflight- với mã đó để tạo run_id dễ nhận biết và có định danh riêng cho mỗi lần chạy. seq bằng 1 là số thứ tự bản ghi trong lượt kiểm chứng này. environment aws ghi nhận cloud tạo dữ liệu. created_at nhận giá trị mặc định now() từ schema của bảng.

RETURNING in các trường của bản ghi vừa được INSERT để người vận hành sao chép run_id làm điều kiện truy vấn bên Azure. Mong đợi một dòng dữ liệu cùng thông báo INSERT 0 1. Khóa chính (run_id, seq) xác định duy nhất bản ghi. Giữ lại run_id từ output để bước đối chiếu dùng đúng bản ghi vừa tạo.

Checkpoint này là ghi thành công một bản ghi mới trên AWS và lấy run_id. Bước tiếp theo truy vấn theo run_id trên Azure để kiểm chứng WAL đã đưa transaction này tới standby.

Kết quả thực hành trên AWS đã INSERT thành công run_id stage7-preflight-13482cf0-e0f8-41a9-901d-e2177db47853, seq 1, environment aws, created_at 2026-11-14 10:45:20.854422+00. PostgreSQL trả INSERT 0 1.

### 4.9. Đọc bản ghi kiểm chứng trên Azure

Trong terminal SSH Ubuntu của Azure, truy vấn bản ghi vừa tạo trên AWS.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT run_id, seq, environment, created_at
   FROM probe_pings
   WHERE run_id = 'stage7-preflight-13482cf0-e0f8-41a9-901d-e2177db47853'
     AND seq = 1;"
```

Trong mỗi lần tái dựng hoặc chạy lại, thay giá trị run_id bằng mã thực tế lấy từ RETURNING ở mục 4.8. run_id và seq là hai cột của khóa chính, nên điều kiện WHERE xác định đúng bản ghi kiểm chứng. SELECT đọc dữ liệu từ PostgreSQL trên Azure qua Pod postgres-0 của cluster Azure.

Mong đợi một dòng có cùng run_id, seq 1, environment aws và created_at 2026-11-14 10:45:20.854422+00. environment lưu cloud đã tạo bản ghi, nên giá trị aws trên bản đọc từ Azure phù hợp với dữ liệu được replicate. created_at cũng thuộc dữ liệu của transaction gốc và được đối chiếu cùng các trường còn lại.

Với vai trò database, hai đầu streaming và bản ghi mới đã được đối chiếu, checkpoint này xác nhận topology ban đầu AWS primary và Azure standby hoạt động sau lần nghỉ. Bước tiếp theo chuẩn bị cơ chế kiểm soát writer cũ khi máy khởi động lại trước bài thử failover.

Kết quả thực hành trên Azure đã đọc được đúng một dòng với run_id stage7-preflight-13482cf0-e0f8-41a9-901d-e2177db47853, seq 1, environment aws và created_at 2026-11-14 10:45:20.854422+00. Transaction mới trên AWS đã được replicate và replay thành dữ liệu có thể truy vấn trên Azure.

### 4.10. Viết cấu hình kiểm soát khởi động K3s sau reboot

Sau khi failover, Azure sẽ giữ dữ liệu mới với vai trò primary. Disk PostgreSQL của AWS cũ vẫn có trạng thái primary từ trước khi bị fence. Khi VM AWS được bật lại, K3s có thể tự khởi động workload database đó. Cơ chế vận hành cần giữ máy cũ ở trạng thái kiểm soát trong thời gian chuẩn bị rejoin.

Project dùng systemd drop-in cho k3s.service, yêu cầu file phê duyệt trong /run trước khi khởi động K3s. Quyết định này áp dụng cho cả hai cloud vì mỗi cloud đều có thể trở thành writer cũ sau failover hoặc failback. Thư mục /run lưu dữ liệu runtime của boot hiện tại, nên file phê duyệt mất sau reboot. Người vận hành đối chiếu writer thực tế và quy trình phục hồi trước khi cho phép K3s khởi động ở boot mới.

Trong Git Bash trên laptop tại thư mục gốc repository, tạo file cấu hình.

```bash
mkdir -p deploy/systemd
touch deploy/systemd/k3s-start-guard.conf
```

Mở deploy/systemd/k3s-start-guard.conf và nhập nội dung sau.

```ini
[Service]
ExecStartPre=/usr/bin/test -f /run/issues-k3s-start-approved
```

- [Service] chọn nhóm tùy chọn quản lý process của service.
- ExecStartPre khai báo lệnh chạy trước lệnh khởi động K3s. systemd yêu cầu lệnh này kết thúc thành công để tiếp tục khởi động service.
- /usr/bin/test -f kiểm tra đường dẫn có tồn tại và là regular file. Khi có file, test trả exit code 0. Khi thiếu file, test trả exit code khác 0 và bước khởi động bị chặn.
- /run/issues-k3s-start-approved là marker ghi nhận sự phê duyệt cho boot hiện tại. Nội dung file có thể rỗng, điều kiện kiểm tra là sự tồn tại của file.

File cấu hình được cài vào thư mục k3s.service.d ở bước tiếp theo để systemd đọc cùng unit K3s hiện có. Guard thực thi kiểm tra file, còn việc xác minh vai trò database và cho phép khởi động thuộc thao tác vận hành. Khi thay đổi vai trò trong cùng boot, runbook phải quản lý marker tương ứng. Fencing bằng cloud API và xác nhận VM dừng vẫn nằm trong luồng failover.

Sau khi cơ chế này được cài và kiểm tra, mỗi lần reboot VM cần đối chiếu writer và phê duyệt khởi động K3s theo vai trò phù hợp. Đây là chi phí vận hành của phương án khởi động có kiểm soát trong lab hai single-node cluster. [systemd service](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html#ExecStartPre=), [PostgreSQL failover](https://www.postgresql.org/docs/17/warm-standby-failover.html).

Checkpoint hiện tại là chuẩn bị file cấu hình trong repository. Bước tiếp theo cài drop-in trên AWS, tạo marker cho boot hiện tại đã xác nhận AWS primary, rồi reload cấu hình systemd.

### 4.11. Cài cấu hình kiểm soát khởi động K3s trên AWS

File deploy/systemd/k3s-start-guard.conf đã được đối chiếu với hai dòng cấu hình ở mục 4.10. Cài file thành systemd drop-in để service K3s sử dụng điều kiện kiểm tra marker ở những lần khởi động tiếp theo. Topology hiện tại đã được xác nhận AWS primary, Azure standby và bản ghi mới đã replay trên Azure, nên phê duyệt K3s cho boot AWS đang chạy.

Trong Git Bash trên laptop tại thư mục gốc repository, chuyển file cấu hình lên EC2.

```bash
scp -i ~/.ssh/mcf-lab \
  deploy/systemd/k3s-start-guard.conf \
  ubuntu@175.41.152.242:/home/ubuntu/k3s-start-guard.conf
```

Trong terminal SSH Ubuntu của AWS, cài drop-in, tạo marker và reload cấu hình systemd.

```bash
sudo install -d -m 755 -o root -g root /etc/systemd/system/k3s.service.d

sudo install -m 644 -o root -g root \
  /home/ubuntu/k3s-start-guard.conf \
  /etc/systemd/system/k3s.service.d/10-start-guard.conf

sudo touch /run/issues-k3s-start-approved
sudo systemctl daemon-reload
```

install -d tạo thư mục cấu hình bổ sung cho k3s.service. install -m 644 sao chép file, đặt owner root và quyền root đọc/ghi, các user còn lại đọc. File .conf là dữ liệu cấu hình được systemd đọc. Số 10 trong tên file xác định thứ tự đọc drop-in theo tên.

touch tạo marker phê duyệt cho boot hiện tại đã được kiểm tra. daemon-reload yêu cầu systemd đọc lại unit cùng các drop-in để sử dụng cấu hình mới trong lần khởi động service tiếp theo. [systemd drop-ins](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html), [systemctl daemon-reload](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html#daemon-reload).

Đối chiếu cấu hình đã nạp, marker và trạng thái dịch vụ.

```bash
sudo systemctl show k3s -p DropInPaths -p ExecStartPre --no-pager --full
sudo ls -l /run/issues-k3s-start-approved
sudo systemctl is-active k3s
```

DropInPaths cần chứa /etc/systemd/system/k3s.service.d/10-start-guard.conf. ExecStartPre cần có /usr/bin/test -f /run/issues-k3s-start-approved trong danh sách lệnh trước khi khởi động K3s. ls cần hiển thị marker thuộc root. is-active cần trả active cho service đang chạy.

Nếu terminal hiển thị (END), systemctl đang mở output bằng pager. Nhấn q để quay về shell rồi chạy lại các lệnh kiểm tra. no-pager hiển thị trực tiếp và full hiển thị đầy đủ các trường. Các dòng modprobe br_netfilter và modprobe overlay thuộc cấu hình chuẩn bị kernel module của K3s. Dòng test của drop-in được bổ sung vào danh sách ExecStartPre với ignore_errors=no, khiến kết quả kiểm tra marker quyết định việc tiếp tục khởi động. Output thực hành đã xác nhận DropInPaths cùng lệnh test được nạp trên AWS. Cần đối chiếu thêm marker và trạng thái active để hoàn tất checkpoint cài đặt.

Checkpoint này xác nhận drop-in đã được cài và systemd đã nạp điều kiện, cùng marker phê duyệt cho boot hiện tại. Bài kiểm tra hành vi chặn khởi động được thực hiện ở bước kiểm chứng riêng sau khi cấu hình trên cả hai cloud.

Kết quả thực hành AWS đã xác nhận ExecStartPre có lệnh test marker với ignore_errors=no, DropInPaths trỏ đúng 10-start-guard.conf, marker là file rỗng thuộc root:root và k3s đang active. Checkpoint cài đặt AWS đã đạt.

### 4.12. Cài cấu hình kiểm soát khởi động K3s trên Azure

Azure hiện là standby và có thể trở thành primary trong bài thử failover. Khi thực hành failback, Azure có thể trở thành writer cũ cần đưa về standby. Cài cùng drop-in để kiểm soát khởi động workload sau reboot trên cả hai VM.

Trong Git Bash trên laptop tại thư mục gốc repository, chuyển file lên Azure.

```bash
scp -i ~/.ssh/mcf-lab \
  deploy/systemd/k3s-start-guard.conf \
  azureuser@4.145.30.250:/home/azureuser/k3s-start-guard.conf
```

Trong terminal SSH Ubuntu của Azure, cài drop-in và phê duyệt boot hiện tại đã xác nhận database là standby.

```bash
sudo install -d -m 755 -o root -g root /etc/systemd/system/k3s.service.d

sudo install -m 644 -o root -g root \
  /home/azureuser/k3s-start-guard.conf \
  /etc/systemd/system/k3s.service.d/10-start-guard.conf

sudo touch /run/issues-k3s-start-approved
sudo systemctl daemon-reload
```

Các lệnh có cùng chức năng như mục 4.11, thực hiện trên host Azure. Cấu hình được lưu trong /etc/systemd/system của VM Azure và marker nằm trong /run của chính VM này. Hai host quản lý file cùng tên trong filesystem riêng.

Kiểm tra cấu hình, marker và service trên Azure.

```bash
sudo systemctl show k3s -p DropInPaths -p ExecStartPre --no-pager --full
sudo ls -l /run/issues-k3s-start-approved
sudo systemctl is-active k3s
```

Mong đợi DropInPaths trỏ đúng 10-start-guard.conf, ExecStartPre có lệnh /usr/bin/test -f /run/issues-k3s-start-approved với ignore_errors=no, marker thuộc root:root và K3s active. Checkpoint này xác nhận cấu hình đã được nạp trên Azure. Bước tiếp theo kiểm chứng hành vi khởi động sau reboot trong trạng thái topology đã xác định.

Kết quả thực hành Azure đã xác nhận drop-in 10-start-guard.conf được nạp, ExecStartPre có lệnh test marker với ignore_errors=no, marker là file rỗng thuộc root:root và K3s active. Checkpoint cài đặt Azure đã đạt.

### 4.13. Kiểm chứng startup guard bằng reboot Azure

Kiểm tra hành vi thực tế bằng reboot VM Azure đang giữ vai trò standby. AWS primary tiếp tục phục vụ ứng dụng trong phép thử, còn Azure tạm gián đoạn replication. Reboot tạo boot mới, giúp kiểm chứng marker trong /run bị xóa và điều kiện ExecStartPre thực sự chặn K3s trước khi workload database khởi động.

Trong terminal SSH Ubuntu của Azure, chạy lệnh sau.

```bash
sudo reboot
```

reboot yêu cầu hệ điều hành khởi động lại VM. Kết nối SSH sẽ ngắt khi hệ điều hành shutdown. Sau khoảng 30–60 giây, mở lại SSH từ Git Bash trên laptop. Thời gian thực tế phụ thuộc quá trình boot của VM.

```bash
ssh -i ~/.ssh/mcf-lab azureuser@4.145.30.250
```

Trong terminal Ubuntu của Azure sau khi kết nối lại, kiểm tra marker và ghi nhận exit code ngay sau lệnh test.

```bash
sudo test -f /run/issues-k3s-start-approved
echo $?
```

test -f kiểm tra file marker. Biến shell $? là exit code của lệnh ngay trước đó, echo in giá trị đó. Mong đợi 1, biểu thị điều kiện file tồn tại không thỏa sau reboot.

Đối chiếu nguyên nhân K3s bị chặn.

```bash
sudo systemctl status k3s --no-pager --full
```

Mong đợi thấy lệnh ExecStartPre /usr/bin/test -f /run/issues-k3s-start-approved kết thúc với status=1/FAILURE. Service có thể hiển thị failed hoặc activating (auto-restart) tùy thời điểm do cấu hình tự thử khởi động lại của K3s. Output status có thể trả exit code khác 0 cho service đang bị chặn. [systemd ExecStartPre](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html#ExecStartPre=).

Kiểm tra trạng thái cổng PostgreSQL trên host.

```bash
sudo ss -ltnp 'sport = :5432'
```

ss liệt kê socket, -l chọn socket lắng nghe, -t chọn TCP, -n hiển thị địa chỉ/cổng dạng số và -p hiển thị process. Điều kiện sport = :5432 lọc cổng PostgreSQL. Mong đợi bảng chỉ có tiêu đề, tức không có socket TCP 5432 đang lắng nghe. Kết quả giúp đối chiếu rằng database Azure đã dừng sau reboot trong khi K3s bị guard chặn.

Checkpoint hiện tại là marker mất sau reboot, K3s bị chặn bởi đúng lệnh test và cổng PostgreSQL chưa mở. Bước tiếp theo đối chiếu AWS vẫn là writer, rồi phê duyệt boot Azure để khôi phục standby và kiểm tra lại replication.

Kết quả thực hành sau reboot Azure đã trả exit code 1 cho phép kiểm tra marker. systemctl status hiển thị activating (auto-restart), ExecStartPre test marker kết thúc status=1/FAILURE. ss cho cổng 5432 chỉ có dòng tiêu đề. Điều kiện kiểm soát khởi động đã chặn K3s và PostgreSQL sau boot mới như dự kiến.

### 4.14. Xác nhận writer và phê duyệt boot Azure sau phép thử

Khôi phục Azure thành standby sau phép thử reboot. Azure đã được xác nhận standby trước reboot. Đối chiếu AWS hiện vẫn giữ vai trò primary trước khi phê duyệt boot Azure để tiếp tục topology này.

Trong terminal SSH Ubuntu của AWS, chạy lại truy vấn vai trò.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT pg_is_in_recovery() AS in_recovery,
          current_setting('transaction_read_only') AS read_only;"
```

Mong đợi f và off. Câu SQL có cùng ý nghĩa như mục 4.6, dùng để đối chiếu writer ngay trước quyết định phê duyệt boot mới của Azure. Khi kết quả khớp topology này, chạy các lệnh sau trong terminal SSH Ubuntu của Azure.

```bash
sudo systemctl stop k3s
sudo touch /run/issues-k3s-start-approved
sudo systemctl reset-failed k3s
sudo systemctl start k3s
```

stop dừng vòng auto-restart đang thử khởi động K3s khi thiếu marker. touch tạo marker cho boot Azure hiện tại. reset-failed xóa trạng thái lỗi cùng bộ đếm giới hạn khởi động của service sau các lần kiểm tra thất bại. start yêu cầu systemd chạy K3s, lúc này lệnh test marker có thể trả thành công. [systemctl](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html).

Đối chiếu service và chờ PostgreSQL Pod sẵn sàng trên Azure.

```bash
sudo systemctl is-active k3s
sudo k3s kubectl -n issues rollout status statefulset/postgres --timeout=180s
sudo k3s kubectl -n issues get pods -o wide
```

Mong đợi active, rollout PostgreSQL thành công và postgres-0 cùng issues-app đạt 1/1 Running sau khi khởi động ổn định. rollout status chờ điều kiện sẵn sàng của StatefulSet thay vì truy vấn ngay khi workload còn khởi động. Bước tiếp theo đối chiếu lại Azure t/on cùng WAL streaming để xác nhận standby đã phục hồi sau phép thử guard.

Checkpoint này áp dụng cho lượt reboot kiểm tra Azure với topology AWS primary, Azure standby đã xác định. Khi VM là writer cũ sau một lần chuyển vai trò, quyết định phê duyệt phải theo quy trình rejoin và trạng thái dữ liệu tại thời điểm đó.

Kết quả thực hành sau phê duyệt boot Azure đã trả K3s active, rollout StatefulSet PostgreSQL thành công, postgres-0 cùng issues-app 1/1 Running. App Pod dùng IP 10.42.0.35 tại thời điểm kiểm tra.

### 4.15. Xác nhận Azure phục hồi standby và WAL receiver sau phép thử guard

K3s và workload đã hoạt động trở lại sau khi phê duyệt boot Azure. Truy vấn database để đối chiếu vai trò cùng kết nối WAL, vì việc process chạy và Pod Ready cần được nghiệm thu cùng trạng thái replication trước bước failover.

Trong terminal SSH Ubuntu của Azure, chạy một lần psql với hai câu SELECT.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT pg_is_in_recovery() AS in_recovery,
          current_setting('transaction_read_only') AS read_only;
   SELECT status, sender_host, sender_port,
          pg_last_wal_receive_lsn() AS receive_lsn,
          pg_last_wal_replay_lsn() AS replay_lsn
   FROM pg_stat_wal_receiver;"
```

psql thực thi hai câu SELECT và hiển thị hai bảng kết quả. Câu đầu xác nhận PostgreSQL Azure tiếp tục chạy recovery với transaction read-only. Câu thứ hai xác nhận WAL receiver kết nối lại đúng AWS primary qua WireGuard.

| Bảng kết quả | Điều kiện mong đợi |
|---|---|
| Vai trò | in_recovery t, read_only on |
| WAL receiver | Một dòng, status streaming, sender_host 10.200.29.1, sender_port 5432 |

receive_lsn và replay_lsn thể hiện tiến độ nhận và replay WAL sau lần khởi động lại. Giá trị có thể tiến lên so với lượt kiểm tra trước. Khi ít tải và standby bắt kịp, hai vị trí thường bằng nhau. Các hàm và system view được giải thích ở mục 4.6 và 4.7.

Checkpoint này hoàn tất khi Azure giữ vai trò standby và đã nhận WAL từ đúng AWS primary. Phép thử guard đã bao gồm boot mới bị chặn khi thiếu marker, phê duyệt có kiểm soát, khởi động lại workload và đối chiếu replication. Bước tiếp theo chuẩn bị bài thử mất môi trường AWS và luồng xác nhận fencing trước promote.

Kết quả thực hành Azure sau phê duyệt boot đã xác nhận in_recovery t, read_only on và WAL receiver streaming từ 10.200.29.1:5432. receive_lsn là 0/3000000, replay_lsn là 0/3006F88 trong output này.

### 4.16. Kiểm chứng WAL mới sau khi receiver khởi động lại

Hai giá trị receive_lsn và replay_lsn trong lượt kiểm tra sau reboot có thể phản ánh các mốc khác nhau. Khi WAL receiver khởi động, vị trí flushed ban đầu được khởi tạo theo vị trí bắt đầu nhận, còn recovery có thể replay WAL đã lưu trên disk. Đây là cách giải thích phù hợp với output sau lần restart này, cần đối chiếu thêm transaction mới để xác nhận luồng nhận WAL hiện tại. [WAL receiver statistics](https://www.postgresql.org/docs/17/monitoring-stats.html#MONITORING-PG-STAT-WAL-RECEIVER-VIEW), [PostgreSQL WAL receiver initialization](https://github.com/postgres/postgres/blob/REL_17_STABLE/src/backend/replication/walreceiverfuncs.c).

Trong terminal SSH Ubuntu của AWS, ghi một bản ghi có định danh mới để đánh dấu thời điểm sau phép thử guard.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "INSERT INTO probe_pings (run_id, seq, environment)
   VALUES ('stage7-after-guard-' || gen_random_uuid()::text, 1, 'aws')
   RETURNING run_id, seq, environment, created_at;"
```

Câu INSERT sử dụng cùng bảng và cấu trúc như mục 4.8. Tiền tố stage7-after-guard- nhận diện phép kiểm tra mới phát sinh sau khi receiver được bật lại. UUID tạo run_id riêng cho mỗi lần thực hành. RETURNING in định danh cùng dữ liệu để dùng trong truy vấn trên Azure.

Mong đợi một dòng bản ghi và INSERT 0 1. Giữ run_id để truy vấn chính xác bản ghi này trên Azure, đồng thời kiểm tra lại receive_lsn và replay_lsn sau khi có WAL mới. Checkpoint này xác nhận replication có thể tiếp nhận và áp dụng transaction mới sau vòng reboot, chặn K3s rồi phê duyệt khởi động.

Kết quả AWS đã INSERT thành công run_id stage7-after-guard-e36c462b-f637-49f6-8dc8-f8c89c92296e, seq 1, environment aws và created_at 2026-11-14 11:35:33.652496+00. PostgreSQL trả INSERT 0 1.

### 4.17. Đối chiếu transaction sau phép thử guard trên Azure

Trong terminal SSH Ubuntu của Azure, chạy hai câu SELECT để đối chiếu bản ghi mới và tiến độ WAL receiver.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT run_id, seq, environment, created_at
   FROM probe_pings
   WHERE run_id = 'stage7-after-guard-e36c462b-f637-49f6-8dc8-f8c89c92296e'
     AND seq = 1;
   SELECT status, sender_host,
          pg_last_wal_receive_lsn() AS receive_lsn,
          pg_last_wal_replay_lsn() AS replay_lsn
   FROM pg_stat_wal_receiver;"
```

Khi thực hành lại, dùng run_id lấy từ RETURNING ở mục 4.16. Câu SELECT đầu lọc theo khóa chính (run_id, seq), xác nhận transaction mới sau reboot và phê duyệt K3s đã xuất hiện trên Azure. Mong đợi một dòng với environment aws cùng created_at 2026-11-14 11:35:33.652496+00 từ transaction gốc.

Câu SELECT thứ hai xác nhận receiver tiếp tục streaming từ 10.200.29.1 và đối chiếu vị trí nhận, replay sau WAL mới. Các LSN cần được đọc theo thời điểm thực tế. Khi standby bắt kịp và ít tải ghi, receive_lsn và replay_lsn thường bằng nhau. Bằng chứng bản ghi hiện diện trên Azure xác nhận transaction tương ứng đã được áp dụng và truy vấn được trên standby.

Checkpoint này hoàn tất khi có bản ghi đúng định danh và receiver đang streaming. Tiếp theo chuẩn bị bài thử mất môi trường AWS, xác nhận fencing và promote theo trình tự duy trì một writer.

Kết quả Azure đã xác nhận bản ghi stage7-after-guard-e36c462b-f637-49f6-8dc8-f8c89c92296e với đúng seq, environment và created_at. WAL receiver streaming từ 10.200.29.1, receive_lsn và replay_lsn đều là 0/30072A0. Transaction mới đã được nhận và replay sau vòng reboot, chặn K3s rồi phê duyệt boot.

### 4.18. Mô phỏng mất môi trường AWS và xác nhận fencing

Điều kiện bắt đầu đã được đối chiếu gồm AWS primary, Azure standby, WAL streaming, transaction mới xuất hiện trên Azure và drop-in kiểm soát khởi động đã nạp trên cả hai host. Phép thử trên Azure đã xác nhận marker mất sau reboot và K3s bị chặn đúng điều kiện, sau đó standby được khôi phục thành công.

Bài thử đầu dùng AWS StopInstances theo chế độ shutdown thông thường để làm mất khả dụng toàn bộ workload trên VM AWS. AWS thực hiện graceful OS shutdown theo mặc định. EC2 dừng khiến PostgreSQL, ứng dụng và các dịch vụ trên VM dừng theo. EBS lưu dữ liệu phục vụ bước rejoin. Từ lúc AWS dừng tới khi Azure writer và đường truy cập sẵn sàng, ứng dụng có khoảng gián đoạn.

Fencing ở bước này là dùng cloud API để dừng writer cũ và đối chiếu trạng thái Stopped. Khi kết nối mạng bị gián đoạn, writer cũ vẫn có thể hoạt động. Xác nhận cloud đã dừng EC2 cung cấp điều kiện để tiến hành promote Azure trong lượt thực hành này.

Trong Git Bash trên laptop tại thư mục gốc repository, yêu cầu dừng đúng instance AWS của project.

```bash
aws ec2 stop-instances \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids i-014ee6f4d204aacb7 \
  --no-cli-pager
```

stop-instances gửi yêu cầu shutdown EC2. profile, region và instance-ids xác định account, Singapore region cùng VM đã đối chiếu. Response thường ghi PreviousState running và CurrentState stopping. stopping biểu thị yêu cầu đang được xử lý. [AWS StopInstances](https://docs.aws.amazon.com/cli/latest/reference/ec2/stop-instances.html).

Chờ AWS xác nhận instance đã dừng.

```bash
aws ec2 wait instance-stopped \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids i-014ee6f4d204aacb7
```

Waiter gọi DescribeInstances định kỳ cho tới khi State.Name là stopped. Khi thành công, lệnh trả lại prompt với exit code 0. [AWS instance-stopped waiter](https://docs.aws.amazon.com/cli/latest/reference/ec2/wait/instance-stopped.html).

Lấy bằng chứng trạng thái để lưu cùng lượt thực hành.

```bash
aws ec2 describe-instances \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids i-014ee6f4d204aacb7 \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name}' \
  --output table \
  --no-cli-pager
```

Mong đợi Id i-014ee6f4d204aacb7 và State stopped. describe-instances in trạng thái rõ ràng để đối chiếu bằng chứng fencing. Checkpoint của bước này là xác nhận writer AWS đã bị fence. Bước promote Azure được hướng dẫn tiếp sau khi có kết quả stopped.

Người vận hành đã xác nhận EC2 AWS ở trạng thái stopped sau bước fencing. Lượt thực hành tiếp tục với AWS giữ trạng thái dừng và Azure hiện là standby.

### 4.19. Promote PostgreSQL Azure thành primary

Điều kiện bắt đầu là AWS đã được fence và xác nhận stopped ở mục 4.18. Promote yêu cầu PostgreSQL Azure kết thúc recovery để trở thành primary. Thao tác này chuyển vai trò database hiện có trên PVC Azure, sử dụng dữ liệu WAL đã nhận và replay.

Trong terminal SSH Ubuntu của Azure, chạy lệnh sau.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT pg_promote(true, 60) AS promoted;"
```

pg_promote là hàm quản trị PostgreSQL dùng để promote standby. Tham số true yêu cầu chờ promote hoàn tất, tham số 60 đặt giới hạn chờ 60 giây. AS promoted đặt tên cột kết quả. Mong đợi promoted t, biểu thị PostgreSQL đã xác nhận promote thành công. Giá trị f biểu thị chưa xác nhận hoàn tất trong thời gian chờ và cần đối chiếu trạng thái thực tế trước bước tiếp theo. [PostgreSQL pg_promote](https://www.postgresql.org/docs/17/functions-admin.html#FUNCTIONS-RECOVERY-CONTROL).

Sau khi promoted t, mở một kết nối psql mới để kiểm tra vai trò và cờ cho phép ghi của ứng dụng.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT pg_is_in_recovery() AS in_recovery,
          current_setting('transaction_read_only') AS read_only,
          writes_enabled
   FROM app_control
   WHERE singleton = TRUE;"
```

Các tham số kubectl và psql giữ cùng ý nghĩa như mục 4.6. Kết nối mới kiểm tra chế độ transaction sau khi vai trò database đã thay đổi. Hai cột đầu đối chiếu trạng thái PostgreSQL, còn writes_enabled là cờ ứng dụng đọc từ bảng app_control để quyết định cho phép ghi. Điều kiện singleton = TRUE chọn dòng điều khiển duy nhất của ứng dụng.

Mong đợi in_recovery f, read_only off và writes_enabled t. Trong lượt triển khai hiện tại, cờ ứng dụng có giá trị true từ primary AWS và được replicate cùng dữ liệu. Khi PostgreSQL trở thành primary và cờ này true, logic database/role.py trả writable true và /health/database trả HTTP 200. Health check Route 53 có thể đánh giá Azure healthy rồi chọn record SECONDARY cho hostname chung khi AWS unhealthy.

Promote tạo nhánh WAL timeline mới cho primary Azure. Bước rejoin AWS sẽ đồng bộ theo writer hiện tại để chuẩn bị standby. Checkpoint hiện tại là promote được xác nhận và truy vấn vai trò đạt f/off/t. Bước tiếp theo kiểm tra writer health qua HTTPS, DNS hostname chung và giao dịch ghi qua ứng dụng.

Kết quả PostgreSQL trên Azure sau promote đã xác nhận in_recovery f, read_only off và writes_enabled t. Azure đã giữ vai trò primary với cờ ứng dụng cho phép ghi trong khi AWS đã được fence.

### 4.20. Kiểm tra writer health, DNS và hostname chung sau promote

Sau khi đối chiếu vai trò PostgreSQL trên Azure, kiểm tra đường truy cập từ laptop bên ngoài hai môi trường. Ba phép kiểm tra xác nhận origin Azure có writer health tốt, Route 53 chọn SECONDARY và request qua hostname chung tới ứng dụng Azure.

Trong Git Bash trên laptop, kiểm tra writer health origin Azure.

```bash
/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://azure.mcf.todicode.tech/health/database
```

Lệnh dùng Windows curl đã được kiểm chứng, xác minh TLS và truy cập origin Azure. fsS hiển thị lỗi HTTP và lỗi kết nối, max-time 10 giới hạn thời gian request, còn w in thêm HTTP status code. Mong đợi HTTP 200, connected true, role primary, writable true và writes_paused false. Kết quả này xác nhận ứng dụng kết nối được với database writer mới.

Kiểm tra CNAME của hostname chung qua resolver 1.1.1.1.

```bash
nslookup -type=CNAME app.mcf.todicode.tech 1.1.1.1
```

Mong đợi canonical name azure.mcf.todicode.tech. Route 53 chọn SECONDARY khi health check AWS unhealthy và Azure healthy. Health check cần thời gian đánh giá, các resolver cũng có cache với thời hạn riêng. Khi đang chuyển trạng thái, kiểm tra lại sau khi các health checker đánh giá và cache hết hạn. TTL CNAME hiện là 30 giây.

Kiểm tra ứng dụng qua hostname chung bằng đường phân giải DNS thông thường của laptop.

```bash
/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://app.mcf.todicode.tech/version
```

Mong đợi HTTP 200 với environment azure, region southeastasia và commit_sha c56fd3f30baee50fa779607dc0fb1a2133b53a9d. Resolver của laptop có thể giữ cache khác với resolver 1.1.1.1 được chọn ở lệnh nslookup, nên đối chiếu cả kết quả DNS và request ứng dụng.

Checkpoint này hoàn tất khi writer health Azure đạt 200, CNAME chọn Azure và request hostname chung trả environment azure. Bước tiếp theo ghi dữ liệu qua ứng dụng trên hostname chung, đối chiếu dữ liệu sau failover và chuẩn bị rejoin AWS.

Kết quả thực hành đã xác nhận resolver 1.1.1.1 trả CNAME app.mcf.todicode.tech tới azure.mcf.todicode.tech. Request HTTPS /version qua hostname chung trả HTTP 200, environment azure, region southeastasia và commit_sha c56fd3f30baee50fa779607dc0fb1a2133b53a9d, tại 2026-11-14 11:47:01.921906+00:00.

### 4.21. Ghi và đọc dữ liệu qua hostname chung sau failover

Đường truy cập hostname chung đã tới Azure. Kiểm tra request ghi để nghiệm thu ứng dụng có thể thực hiện transaction trên writer mới. Endpoint POST /api/ping của project kiểm tra vai trò database, cờ writes_enabled và ghi vào probe_pings qua cùng write barrier được dùng cho nghiệp vụ issue.

Trong Git Bash trên laptop, tạo mã lượt kiểm chứng và gửi JSON body qua stdin của Windows curl.

```bash
MCF_FAILOVER_RUN_ID="stage7-failover-$(date -u +%Y%m%dT%H%M%SZ)"

printf '{"run_id":"%s","seq":1}\n' "$MCF_FAILOVER_RUN_ID" |
  /c/Windows/System32/curl.exe -fsS --max-time 10 \
    -H 'Content-Type: application/json' \
    --data-binary @- \
    -w '\nHTTP %{http_code}\n' \
    https://app.mcf.todicode.tech/api/ping
```

MCF_FAILOVER_RUN_ID là biến trong terminal Git Bash hiện tại. date -u tạo thời gian UTC, định dạng năm/tháng/ngày và giờ/phút/giây để nhận diện lượt kiểm chứng. Command substitution $(...) đặt output của date vào chuỗi run_id. Dấu ngoặc kép giữ chuỗi trong một giá trị biến.

printf tạo JSON body, thay %s bằng run_id của lượt này. Pipe truyền body sang curl. Header Content-Type application/json cho FastAPI biết kiểu dữ liệu. data-binary @- đọc body từ stdin và khiến curl gửi POST. Cách truyền JSON qua stdin phù hợp khi gọi executable Windows từ Git Bash. Các tùy chọn fsS, max-time và w có cùng ý nghĩa như mục 4.20.

Mong đợi HTTP 200 với run_id của lượt này, seq 1 và environment azure. Ứng dụng lấy environment từ runtime APP_ENV của instance xử lý request. Endpoint ghi probe có xử lý trùng khóa (run_id, seq), cho phép kiểm tra lại cùng request mà giữ một bản ghi cho cùng định danh.

Trong cùng terminal Git Bash để sử dụng biến đã tạo, đọc lại dữ liệu qua API.

```bash
/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  "https://app.mcf.todicode.tech/api/ping/$MCF_FAILOVER_RUN_ID"
```

Mong đợi HTTP 200, count 1 và một phần tử trong pings với seq 1, environment azure. GET đọc dữ liệu đã lưu trong PostgreSQL, giúp đối chiếu kết quả của request ghi. Giữ run_id và output để sử dụng làm dữ liệu kiểm chứng khi AWS rejoin từ Azure.

Checkpoint này hoàn tất khi POST thành công và GET trả bản ghi đúng định danh, cùng environment azure. Bước tiếp theo đối chiếu dữ liệu trước sự cố và chuẩn bị rejoin AWS từ writer Azure hiện tại.

Kết quả GET qua hostname chung đã trả HTTP 200 với run_id stage7-failover-20261114T121609Z, count 1 và pings chứa seq 1, environment azure. Request ghi sau failover đã tạo dữ liệu có thể đọc lại qua ứng dụng đang phục vụ từ Azure. Giữ định danh này để đối chiếu sau khi rejoin AWS.

### 4.22. Đối chiếu dữ liệu trước sự cố và writer health qua hostname chung

Đã ghi và đọc được dữ liệu mới trên writer Azure. Đọc bản ghi kiểm chứng được tạo trên AWS trước fencing để đối chiếu dữ liệu qua đường truy cập ứng dụng sau chuyển vai trò.

Trong Git Bash trên laptop, chạy lệnh sau.

```bash
/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://app.mcf.todicode.tech/api/ping/stage7-after-guard-e36c462b-f637-49f6-8dc8-f8c89c92296e
```

GET chọn run_id đã tạo ở mục 4.16. Mong đợi HTTP 200, count 1 và bản ghi seq 1, environment aws. environment trong response của endpoint đọc probe thuộc dữ liệu đã lưu, cho biết bản ghi được tạo ở AWS. /version và record tạo sau failover xác định ứng dụng hiện đang phục vụ từ Azure.

Tiếp theo kiểm tra writer health qua hostname chung.

```bash
/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://app.mcf.todicode.tech/health/database
```

Mong đợi HTTP 200 với connected true, role primary, writable true và writes_paused false. Phép kiểm tra này đối chiếu ứng dụng truy cập qua hostname chung đang kết nối tới database có khả năng ghi.

Checkpoint này bổ sung bằng chứng dữ liệu kiểm chứng trước sự cố còn truy vấn được, cùng trạng thái writer qua đường truy cập người dùng. Các bản ghi kiểm chứng phục vụ xác minh lượt thực hành. Đánh giá mất acknowledged writes và RPO của workload được thực hiện bằng bộ đo có thiết kế riêng ở giai đoạn 9. Bước tiếp theo chuẩn bị rejoin AWS thành standby từ dữ liệu của Azure primary.

Kết quả GET bản ghi trước sự cố qua hostname chung đã trả HTTP 200, count 1 và environment aws cho stage7-after-guard-e36c462b-f637-49f6-8dc8-f8c89c92296e. Writer health qua hostname chung trả HTTP 200 với connected true, role primary, writable true, writes_paused false và current_lsn 0/30079F0. Cùng với version azure và bản ghi mới environment azure, các kết quả nghiệm thu luồng failover thủ công từ AWS sang Azure trong lượt thực hành này.

### 4.23. Bật AWS để chuẩn bị rejoin với K3s bị chặn

Azure đang là primary phục vụ ứng dụng và đã phát sinh dữ liệu mới sau failover. AWS cần được dựng lại thành standby theo dữ liệu của writer Azure. Bước đầu khởi động EC2 để SSH vào host và đối chiếu startup guard trước khi chuẩn bị storage cùng cấu hình rejoin.

Trong Git Bash trên laptop, bật EC2 AWS hiện có và chờ status checks.

```bash
aws ec2 start-instances \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids i-014ee6f4d204aacb7 \
  --no-cli-pager

aws ec2 wait instance-status-ok \
  --profile default \
  --region ap-southeast-1 \
  --instance-ids i-014ee6f4d204aacb7
```

Hai lệnh có cùng ý nghĩa như mục 4.2, khởi động VM rồi chờ tình trạng hạ tầng và instance đạt. Trong lượt rejoin này, trạng thái ứng dụng và database trên AWS phải được kiểm soát riêng bằng guard. Sau khi waiter thành công, SSH từ Git Bash.

```bash
ssh -i ~/.ssh/mcf-lab ubuntu@175.41.152.242
```

Trong terminal SSH Ubuntu của AWS, đối chiếu trạng thái guard cùng cổng database.

```bash
sudo test -f /run/issues-k3s-start-approved
echo $?
sudo systemctl status k3s --no-pager --full
sudo ss -ltnp 'sport = :5432'
```

Mong đợi exit code 1 của test, K3s bị chặn ở ExecStartPre với status=1/FAILURE, và bảng socket cổng 5432 chỉ có tiêu đề. Cách đọc các lệnh đã được kiểm chứng trên Azure ở mục 4.13. Lần kiểm tra này xác nhận guard trên chính host AWS cũ trước rejoin.

Giữ K3s ở trạng thái bị guard chặn trong checkpoint này. AWS cũ còn dữ liệu của primary trước sự cố. Cấu hình workload và storage cho standby cần được chuẩn bị trước khi cho phép workload hoạt động. Bước tiếp theo chuẩn bị chế độ vận hành control plane và storage mới phục vụ rejoin từ Azure.

Kết quả AWS sau bật lại đã xác nhận marker mất với test trả 1, K3s bị chặn tại ExecStartPre status=1/FAILURE và cổng 5432 chưa lắng nghe. Host AWS đã sẵn sàng để chuẩn bị rejoin trong khi PostgreSQL cũ giữ trạng thái dừng.

### 4.24. Chuẩn bị cấu hình K3s chỉ chạy control plane khi rejoin

K3s single-node hiện chạy cả control plane và agent trên cùng VM. Control plane cung cấp Kubernetes API cùng các controller quản lý trạng thái cluster. Agent gồm kubelet, container runtime và các thành phần node thực thi Pod. Khi bật K3s theo cấu hình thông thường, agent có thể khởi động lại Pod PostgreSQL cũ dựa trên trạng thái đã lưu.

Quy trình rejoin sử dụng tạm chế độ agentless để bật Kubernetes API phục vụ sửa workload và storage trước khi cho agent thực thi Pod. K3s hỗ trợ cấu hình disable-agent cho mục đích vận hành control plane độc lập với agent trên host. Tài liệu K3s đánh dấu tính năng agentless là experimental. Trong lab này chế độ đó được dùng tạm trong lượt bảo trì rejoin, sau đó agent được bật lại khi workload đã trỏ tới storage và vai trò phù hợp. [K3s agentless servers](https://docs.k3s.io/advanced#running-agentless-servers-experimental).

Trong Git Bash trên laptop tại thư mục gốc repository, tạo file cấu hình.

```bash
mkdir -p deploy/k3s
touch deploy/k3s/rejoin-control-plane.yaml
```

Mở deploy/k3s/rejoin-control-plane.yaml và nhập dòng sau.

```yaml
disable-agent: true
```

disable-agent là tên tùy chọn của K3s. Giá trị boolean true yêu cầu K3s server chạy với agent trên host được tắt. Kết quả là có Kubernetes API để dùng kubectl, trong khi kubelet và container runtime của K3s trên host giữ trạng thái dừng. Bước này tạo điều kiện scale workload cũ về 0 và chuẩn bị PVC mới trước khi chạy lại Pod.

Đây là cấu hình của process K3s, được đọc từ file cấu hình trên host. Ở bước tiếp theo, file sẽ được cài vào /etc/rancher/k3s/config.yaml.d/99-rejoin.yaml trên AWS. K3s đọc drop-in cùng config.yaml theo thứ tự tên file. [K3s configuration files](https://docs.k3s.io/installation/configuration#configuration-file).

Checkpoint hiện tại là chuẩn bị file cấu hình trong repository. Bước tiếp theo cài cấu hình này lên AWS, rồi phê duyệt khởi động K3s trong chế độ agentless để sửa trạng thái workload cho rejoin.

### 4.25. Khởi động control plane AWS trong chế độ agentless

File deploy/k3s/rejoin-control-plane.yaml đã được đối chiếu và parse YAML thành công với disable-agent true. Mục tiêu bước này là truy cập Kubernetes API để sửa workload cho rejoin, đồng thời giữ agent ở trạng thái tắt để PostgreSQL cũ tiếp tục dừng.

Trong Git Bash trên laptop tại thư mục gốc repository, chuyển cấu hình lên AWS.

```bash
scp -i ~/.ssh/mcf-lab \
  deploy/k3s/rejoin-control-plane.yaml \
  ubuntu@175.41.152.242:/home/ubuntu/rejoin-control-plane.yaml
```

Trong terminal SSH Ubuntu của AWS, dừng vòng auto-restart của K3s, rồi cài file drop-in của K3s.

```bash
sudo systemctl stop k3s

sudo install -d -m 700 -o root -g root /etc/rancher/k3s/config.yaml.d

sudo install -m 600 -o root -g root \
  /home/ubuntu/rejoin-control-plane.yaml \
  /etc/rancher/k3s/config.yaml.d/99-rejoin.yaml

sudo cat /etc/rancher/k3s/config.yaml.d/99-rejoin.yaml
```

install tạo thư mục và cài cấu hình với quyền truy cập cho root. K3s đọc file YAML này khi process bắt đầu chạy, cùng với /etc/rancher/k3s/config.yaml. Số 99 giúp drop-in rejoin được đọc sau các file có thứ tự tên thấp hơn. Đối chiếu nội dung cat là disable-agent: true trước khi phê duyệt khởi động.

Khi file đã đúng, tạo marker và khởi động K3s trong chế độ vừa cài.

```bash
sudo touch /run/issues-k3s-start-approved
sudo systemctl reset-failed k3s
sudo systemctl start k3s
```

Marker cho systemd vượt qua ExecStartPre. Cấu hình disable-agent true yêu cầu process K3s chạy control plane với agent tắt. Quyết định phê duyệt ở bước này gắn với chế độ agentless đã đối chiếu, để chuẩn bị workload và storage cho standby trước khi bật agent trở lại. Chế độ agentless của K3s được tài liệu đánh dấu experimental và được dùng tạm cho lượt rejoin của lab. [K3s agentless servers](https://docs.k3s.io/advanced#running-agentless-servers-experimental).

Đối chiếu Kubernetes API và cổng database.

```bash
sudo k3s kubectl get --raw=/readyz
sudo ss -ltnp 'sport = :5432'
```

get --raw=/readyz gửi request tới endpoint readiness của Kubernetes API server bằng credential trong kubeconfig. Mong đợi ok, xác nhận API sẵn sàng nhận thao tác quản trị. ss tiếp tục đối chiếu TCP 5432 với bảng chỉ có tiêu đề. Hai kết quả kiểm tra hai mục tiêu của bước này là API đã mở và PostgreSQL cũ tiếp tục dừng. [Kubernetes API health endpoints](https://kubernetes.io/docs/reference/using-api/health-checks/).

Node và Pod object cũ có thể còn trong datastore của Kubernetes với trạng thái của lượt chạy trước. Trạng thái tiến trình thực tế trên host cần được đối chiếu cùng API khi vận hành agentless. Bước tiếp theo dùng API để scale workload cũ về 0, rồi chuẩn bị PVC mới và dữ liệu clone từ Azure.

Kết quả thực hành trên AWS đã trả ok cho /readyz và bảng socket TCP 5432 chỉ có tiêu đề. Kubernetes API đã sẵn sàng, PostgreSQL cũ tiếp tục dừng trong checkpoint agentless.

### 4.26. Đặt số replica workload AWS về 0 trước khi đổi storage

Kubernetes API đã truy cập được trong chế độ agentless. Cập nhật desired state của StatefulSet PostgreSQL và Deployment ứng dụng để chuẩn bị rejoin. Desired state được lưu trong datastore của cluster và sẽ điều khiển workload khi agent được bật lại.

Trong terminal SSH Ubuntu của AWS, chạy hai lệnh sau.

```bash
sudo k3s kubectl -n issues scale statefulset/postgres --replicas=0
sudo k3s kubectl -n issues scale deployment/issues-app --replicas=0
```

scale cập nhật số replica mong muốn của resource được chọn. statefulset/postgres quản lý PostgreSQL, deployment/issues-app quản lý ứng dụng và namespace issues chọn phạm vi của project. replicas 0 yêu cầu số Pod phục vụ của mỗi workload bằng 0. [kubectl scale](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_scale/).

Đặt PostgreSQL về 0 để cấu hình workload giữ trạng thái dừng trong lúc đổi PVC và chuẩn bị bản clone mới từ Azure. Đặt ứng dụng về 0 để chỉ khởi động ứng dụng AWS sau khi database standby mới được kiểm tra. PVC postgres-data hiện tại chứa dữ liệu AWS trước sự cố và được giữ phục vụ đối chiếu trong quy trình rejoin.

Đối chiếu trực tiếp số replica mong muốn đã lưu.

```bash
sudo k3s kubectl -n issues get statefulset/postgres deployment/issues-app \
  -o 'custom-columns=KIND:.kind,NAME:.metadata.name,DESIRED:.spec.replicas'
```

custom-columns chọn các trường cần hiển thị. kind là loại resource, metadata.name là tên resource và spec.replicas là số replica mong muốn. Đối chiếu spec.replicas vì agent đang tắt, còn status của Pod object cũ có thể phản ánh lượt chạy trước hoặc quá trình chờ kết thúc.

Kết quả mong đợi.

```text
KIND          NAME         DESIRED
StatefulSet   postgres     0
Deployment    issues-app   0
```

Checkpoint này hoàn tất khi cả hai desired replica đều bằng 0. Bước tiếp theo chuẩn bị PVC mới và cấu hình clone từ Azure primary, sau đó cập nhật workload trước khi bật lại agent.

### 4.27. Chuẩn bị PVC mới cho AWS rejoin

Tiếp tục sau khi cả hai desired replica ở mục 4.26 đã bằng 0. PostgreSQL AWS trước sự cố nằm trên PVC postgres-data. Azure primary đã phát sinh WAL và dữ liệu mới sau promote. Quy trình rejoin chọn lấy base backup mới từ Azure vào một PVC khác, giữ vùng dữ liệu AWS cũ để đối chiếu.

pg_basebackup cần thư mục đích trống để tạo bản sao database. PVC mới cung cấp vùng lưu trữ riêng cho lượt clone. StorageClass local-path-retain sử dụng local-path provisioner của K3s và policy Retain của project. [PostgreSQL pg_basebackup](https://www.postgresql.org/docs/17/app-pgbasebackup.html).

Trong Git Bash trên laptop tại thư mục gốc repository, tạo bản manifest PVC mới từ cấu hình hiện có.

```bash
cp deploy/kubernetes/database/postgres-pvc.yaml \
  deploy/kubernetes/database/postgres-pvc-rejoin-aws.yaml
```

Mở deploy/kubernetes/database/postgres-pvc-rejoin-aws.yaml và đặt metadata.name thành postgres-data-rejoin-aws-01. Nội dung sau khi sửa.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data-rejoin-aws-01
  namespace: issues
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path-retain
  resources:
    requests:
      storage: 5Gi
```

- apiVersion và kind xác định đây là PersistentVolumeClaim thuộc core API v1.
- metadata.name đặt định danh PVC cho lượt AWS rejoin đầu tiên. Tên được dùng trong Job clone và StatefulSet ở các bước tiếp theo.
- namespace issues đặt PVC cùng namespace với PostgreSQL.
- ReadWriteOnce là access mode cho phép mount read-write trên một node.
- storageClassName chọn local-path-retain đã triển khai trên AWS.
- requests.storage 5Gi khai báo nhu cầu dung lượng, cùng mức với PVC ban đầu. Local-path dùng không gian trên filesystem của node. Dung lượng filesystem thực tế cần được kiểm tra trước bước copy dữ liệu.

Tên hậu tố 01 nhận diện lượt rejoin này. Trong những lượt thực hành sau, chọn tên PVC mới phù hợp với lượt clone và cập nhật các tham chiếu tương ứng. Mỗi bản clone cần vùng đích trống cùng định danh được đối chiếu rõ ràng.

StorageClass đang dùng WaitForFirstConsumer, nên PVC có thể ở Pending sau khi apply cho tới khi workload tiêu thụ và provisioner có điều kiện hoạt động. Agent hiện tắt, việc chạy Pod clone sẽ được thực hiện sau khi hoàn tất cấu hình rejoin và bật lại agent. [Kubernetes volume binding mode](https://kubernetes.io/docs/concepts/storage/storage-classes/#volume-binding-mode).

Checkpoint hiện tại là chuẩn bị manifest PVC trong repository. Bước tiếp theo chuyển file lên AWS, apply bằng Kubernetes API đang hoạt động và đối chiếu PVC mới cùng PVC dữ liệu cũ.

### 4.28. Apply PVC mới trên AWS và đối chiếu storage

Manifest postgres-pvc-rejoin-aws.yaml đã được kiểm tra YAML với tên postgres-data-rejoin-aws-01, namespace issues, access mode ReadWriteOnce, storage class local-path-retain và request 5Gi.

Trong Git Bash trên laptop tại thư mục gốc repository, chuyển file lên AWS.

```bash
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/database/postgres-pvc-rejoin-aws.yaml \
  ubuntu@175.41.152.242:/home/ubuntu/postgres-pvc-rejoin-aws.yaml
```

Trong terminal SSH Ubuntu của AWS, apply manifest bằng Kubernetes API đã được khởi động trong chế độ agentless.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-pvc-rejoin-aws.yaml
sudo k3s kubectl -n issues get pvc postgres-data postgres-data-rejoin-aws-01
```

apply -f gửi nội dung manifest tới Kubernetes API để tạo PVC. Lệnh get chọn đúng hai PVC để đối chiếu dữ liệu cũ và yêu cầu storage mới. Kết quả mong đợi tại bước này là postgres-data Bound và postgres-data-rejoin-aws-01 Pending. PVC mới chờ workload tiêu thụ cùng local-path provisioner hoạt động theo cơ chế WaitForFirstConsumer. Agent hiện vẫn tắt.

Kiểm tra filesystem lưu local-path volumes.

```bash
sudo df -h /var/lib/rancher/k3s/storage
sudo du -sh /var/lib/rancher/k3s/storage
```

df -h hiển thị tổng dung lượng, mức đã dùng và dung lượng trống của filesystem chứa thư mục storage. Cột Avail giúp đối chiếu khả năng chứa bản clone mới trong khi giữ dữ liệu cũ. du -sh tổng hợp dung lượng thực tế hiện tại của các local-path volumes. h hiển thị đơn vị dễ đọc như MiB hoặc GiB.

PVC request 5Gi là thông tin Kubernetes dùng trong việc cấp phát volume. Local-path lưu dữ liệu trên filesystem của node, nên việc copy dữ liệu cần được đối chiếu với dung lượng trống thực tế của EBS root và mức dữ liệu hiện có. Chỉ số df và du bổ sung thông tin này trước bước clone.

Checkpoint hiện tại là PVC mới được tạo, PVC cũ còn Bound và dung lượng filesystem đã được đối chiếu. Bước tiếp theo chuẩn bị Job clone từ Azure cùng các tham chiếu tới PVC mới.

Kết quả filesystem AWS đã ghi nhận /dev/root 29G, dùng 4.7G, còn 24G trống và thư mục local-path storage dùng 79M tại thời điểm kiểm tra. Phần dung lượng trống phù hợp với việc giữ bản dữ liệu cũ cùng bản clone mới trong lab hiện tại.

### 4.29. Tạo Secret replication trên cluster AWS cho Job clone

Job clone chạy trên AWS cần credential của role replicator để kết nối Azure primary. Ở giai đoạn 5, file /etc/mcf/replication.env được tạo trên AWS và dùng để đặt mật khẩu role replicator. Credential đó cũng đã được dùng khi clone Azure. Secret postgres-replication trước đây được tạo trong cluster Azure. Lượt AWS rejoin cần Secret tương ứng trong namespace issues của cluster AWS.

Trong terminal SSH Ubuntu của AWS, kiểm tra file credential đã giữ lại từ giai đoạn 5 bằng metadata.

```bash
sudo stat -c '%a %U:%G %n' /etc/mcf/replication.env
```

Mong đợi 600 root:root /etc/mcf/replication.env. stat hiển thị quyền, chủ sở hữu và đường dẫn để đối chiếu đúng file cần dùng.

Tạo hoặc cập nhật Secret từ file trên host AWS.

```bash
sudo k3s kubectl -n issues create secret generic postgres-replication \
  --from-env-file=/etc/mcf/replication.env \
  --dry-run=client -o yaml |
  sudo k3s kubectl apply -f -
```

create secret generic chuẩn bị Secret Opaque chứa các key đọc từ file KEY=value. from-env-file chọn file credential hiện có. dry-run=client cùng o yaml xuất manifest Secret vào pipe, còn apply -f - đọc manifest từ stdin để lưu vào Kubernetes API. sudo cho phép đọc file root và dùng kubeconfig quản trị của cluster AWS. Luồng dữ liệu thực hiện ngay trên VM AWS, với output cuối là thông báo tạo hoặc cập nhật Secret.

Secret sẽ được Job clone tham chiếu qua envFrom để cung cấp REPLICATION_USER và REPLICATION_PASSWORD. Role replicator tồn tại trên Azure sau bản clone PostgreSQL và hiện có quyền phục vụ replication theo cấu hình database. Xác thực thực tế sẽ được đối chiếu khi Job kết nối tới Azure.

Đối chiếu Secret và hai PVC phục vụ lượt rejoin.

```bash
sudo k3s kubectl -n issues describe secret postgres-replication
sudo k3s kubectl -n issues get pvc postgres-data postgres-data-rejoin-aws-01
```

Mong đợi Secret Opaque có REPLICATION_USER 10 bytes và REPLICATION_PASSWORD 64 bytes, PVC postgres-data Bound và PVC postgres-data-rejoin-aws-01 Pending ở checkpoint agentless. describe secret hiển thị tên key và kích thước dữ liệu để đối chiếu các biến Job cần dùng.

Checkpoint này hoàn tất khi Secret replication tồn tại đúng key trên AWS và hai PVC được đối chiếu. Bước tiếp theo chuẩn bị script cùng Job clone trỏ tới Azure primary và PVC mới.

Kết quả trên AWS đã xác nhận Secret postgres-replication có REPLICATION_USER 10 bytes và REPLICATION_PASSWORD 64 bytes. PVC postgres-data Bound trên PV pvc-ab47de01-e885-46d3-8d76-7418af39f2ef với 5Gi. PVC postgres-data-rejoin-aws-01 Pending trong lúc chờ workload và provisioner hoạt động.

### 4.30. Chuẩn bị script clone dùng chung cho AWS và Azure

ConfigMap postgres-clone-script chứa script đã dùng để clone Azure ở giai đoạn 5. Script hiện đặt application_name cố định là mcf-azure-standby trong connection string của pg_basebackup. Lượt AWS rejoin cần tên kết nối thể hiện đúng AWS là standby để đối chiếu từ Azure primary qua pg_stat_replication.

Trên laptop, mở deploy/kubernetes/database/postgres-clone-script.yaml. Thay đoạn gọi pg_basebackup bằng nội dung sau.

```bash
    gosu postgres pg_basebackup \
      -d "host=$SOURCE_DB_HOST port=5432 user=$REPLICATION_USER passfile=$PGPASSFILE application_name=${PGAPPNAME:-mcf-azure-standby} connect_timeout=10" \
      -D "$PGDATA" -R -X stream -c fast -w
```

Phần được bổ sung là biểu thức Bash ${PGAPPNAME:-mcf-azure-standby}. Khi PGAPPNAME có giá trị, script dùng tên đó cho application_name. Khi biến chưa được đặt hoặc rỗng, biểu thức dùng giá trị mặc định mcf-azure-standby. Job Azure hiện tại sử dụng mặc định này. Job AWS rejoin ở bước tiếp theo sẽ đặt PGAPPNAME=mcf-aws-standby.

PGAPPNAME là biến môi trường chuẩn của PostgreSQL client tương ứng với application_name. Tham số application_name trong connection string xác định tên kết nối mà primary quan sát được. Script dùng biến này để gán tên phù hợp với cloud nhận clone. [PostgreSQL environment variables](https://www.postgresql.org/docs/17/libpq-envars.html).

gosu postgres chạy pg_basebackup bằng user postgres. d cung cấp kết nối tới source database cùng password file. D chọn thư mục đích trên PVC. R tạo standby.signal và cấu hình kết nối recovery. X stream lấy WAL trong thời gian copy. c fast yêu cầu checkpoint nhanh để bắt đầu base backup. w dùng thông tin xác thực đã cấp cho chế độ chạy tự động. [pg_basebackup](https://www.postgresql.org/docs/17/app-pgbasebackup.html).

Đoạn thay đổi đã được kiểm tra cú pháp YAML và Bash trên bản nội dung dự kiến. Chuyển manifest sau khi sửa lên AWS từ Git Bash trên laptop.

```bash
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/database/postgres-clone-script.yaml \
  ubuntu@175.41.152.242:/home/ubuntu/postgres-clone-script.yaml
```

Trong terminal SSH Ubuntu của AWS, apply ConfigMap và đối chiếu metadata.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-clone-script.yaml
sudo k3s kubectl -n issues get configmap postgres-clone-script
```

Mong đợi ConfigMap postgres-clone-script tồn tại với DATA 1, tương ứng key clone.sh. Job clone sẽ mount key này làm file /bootstrap/clone.sh để thực thi. Checkpoint này là script có thể chọn tên kết nối theo cloud và ConfigMap sẵn sàng trên AWS. Bước tiếp theo viết manifest Job clone dùng Azure source, PVC mới và PGAPPNAME của AWS standby.

Kết quả AWS đã xác nhận ConfigMap postgres-clone-script được tạo và có DATA 1, tương ứng key clone.sh.

### 4.31. Chuẩn bị Job clone AWS rejoin từ Azure

Job là workload chạy tác vụ clone tới khi hoàn tất. Sau khi Job thành công, StatefulSet PostgreSQL sẽ sử dụng dữ liệu trên PVC mới để chạy standby. Tái sử dụng manifest Job clone đã thực hành trên Azure, rồi chọn source, storage và định danh phù hợp cho AWS rejoin.

Trong Git Bash trên laptop tại thư mục gốc repository, tạo file Job mới.

```bash
cp deploy/kubernetes/database/postgres-clone-azure.yaml \
  deploy/kubernetes/database/postgres-clone-rejoin-aws.yaml
```

Mở deploy/kubernetes/database/postgres-clone-rejoin-aws.yaml và sửa bốn giá trị của lượt rejoin.

| Trường | Giá trị AWS rejoin |
|---|---|
| metadata.name | postgres-clone-rejoin-aws-01 |
| SOURCE_DB_HOST trong env | 10.200.29.2 |
| PGAPPNAME thêm trong env | mcf-aws-standby |
| claimName của volume data | postgres-data-rejoin-aws-01 |

Nội dung đầy đủ sau khi chỉnh sửa.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: postgres-clone-rejoin-aws-01
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
              value: "10.200.29.2"
            - name: PGAPPNAME
              value: "mcf-aws-standby"
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
            claimName: postgres-data-rejoin-aws-01
        - name: script
          configMap:
            name: postgres-clone-script
```

metadata.name nhận diện Job của lượt AWS rejoin đầu tiên. SOURCE_DB_HOST chọn IP WireGuard của Azure primary. PGAPPNAME gán tên kết nối cho AWS standby thông qua script đã chuẩn bị. claimName chọn PVC mới đã tạo, là nơi Job ghi dữ liệu clone. Secret postgres-replication cung cấp user và password, ConfigMap postgres-clone-script cung cấp script.

hostNetwork true cho container dùng mạng host AWS để kết nối tới 10.200.29.2 qua WireGuard. volumeMounts đặt dữ liệu ở /var/lib/postgresql/data và script ở /bootstrap. command chạy Bash để thực thi script clone. Resource requests và limits dùng mức đã thực hành cho tác vụ base backup.

backoffLimit 0 ghi nhận thất bại khi Job gặp lỗi để người vận hành xem log và kiểm tra vùng đích trước lần thực hiện tiếp theo. activeDeadlineSeconds 600 giới hạn thời gian hoạt động của Job. Job sẽ được apply khi agent AWS hoạt động trở lại và workload cũ đã được chuẩn bị đúng trạng thái để Pod clone có thể chạy trong thời hạn này. [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/).

Checkpoint hiện tại là chuẩn bị manifest trong repository. Bước tiếp theo sửa StatefulSet AWS để trỏ PVC mới với replicas 0 và điều kiện dữ liệu clone hoàn tất, rồi hoàn thiện các điều kiện trước khi bật lại agent và chạy Job.

Manifest postgres-clone-rejoin-aws.yaml đã được kiểm tra YAML và các tham chiếu. Job chọn source 10.200.29.2, PGAPPNAME mcf-aws-standby, Secret postgres-replication, ConfigMap postgres-clone-script và PVC postgres-data-rejoin-aws-01.

### 4.32. Chuẩn bị StatefulSet AWS dùng dữ liệu clone mới

Job chuẩn bị dữ liệu, còn StatefulSet vận hành PostgreSQL sau khi clone hoàn tất. Cập nhật manifest AWS để khai báo PVC rejoin, số replica 0 trong giai đoạn chuẩn bị và điều kiện kiểm tra bản clone trước khi gọi entrypoint PostgreSQL.

Trên laptop, mở deploy/kubernetes/database/postgres-aws.yaml và thực hiện ba thay đổi sau.

Đặt spec.replicas thành 0.

```yaml
spec:
  serviceName: postgres-headless
  replicas: 0
```

Giá trị 0 đưa trạng thái chuẩn bị vào manifest để lượt apply tiếp theo ghi đúng desired state trong lúc rejoin. Sau khi Job clone được nghiệm thu, số replica sẽ được đặt về 1 để chạy database.

Trong containers của PostgreSQL, thêm command giữa image và args theo mẫu đã thực hành ở manifest Azure.

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

bash -ec thực thi đoạn script với chế độ dừng khi một lệnh thất bại. Phép kiểm tra đầu yêu cầu marker .clone-complete, được Job tạo sau khi base backup và các kiểm tra hoàn tất. Phép kiểm tra thứ hai đọc major version trong PG_VERSION và yêu cầu giá trị 17, tương ứng image PostgreSQL đang dùng. Hai điều kiện cho phép workload sử dụng bản clone đã hoàn tất để khởi động.

exec docker-entrypoint.sh "$@" chuyển quyền điều khiển process sang entrypoint của image PostgreSQL với danh sách args. Dấu -- đứng sau nội dung script là giá trị $0 của Bash khi dùng -c, còn các phần tử trong args trở thành tham số $1, $2 và tiếp theo. "$@" giữ từng tham số là một đối số riêng, nên entrypoint nhận postgres -c config_file=/etc/postgresql/postgresql.conf.

Điều kiện bản clone cần thiết vì entrypoint của image PostgreSQL có khả năng khởi tạo database khi gặp data directory mới. Trong lượt rejoin, database cần khởi động từ dữ liệu đã clone và cấu hình recovery do pg_basebackup -R tạo. [PostgreSQL image entrypoint](https://github.com/docker-library/postgres/blob/master/docker-entrypoint.sh).

Trong volume data, đặt claimName thành PVC mới của lượt rejoin.

```yaml
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: postgres-data-rejoin-aws-01
        - name: config
          configMap:
            name: postgres-config
```

Volume data liên kết cùng PVC mà Job ghi base backup. Volume config cung cấp cấu hình PostgreSQL dành cho địa chỉ WireGuard của host AWS. Cấu hình primary_conninfo cùng standby.signal nằm trong PGDATA của bản clone sẽ giúp PostgreSQL kết nối tới writer Azure khi khởi động.

Checkpoint hiện tại là chuẩn bị StatefulSet trên laptop với replicas 0, entrypoint kiểm tra clone và PVC mới. Bước tiếp theo chuyển manifest lên AWS, apply trong chế độ agentless và xử lý các Pod object cũ trước khi bật lại agent.

### 4.33. Apply StatefulSet AWS trong chế độ agentless

Control plane AWS đang chạy với disable-agent: true. API server tiếp nhận manifest, còn việc chạy Pod sẽ được khôi phục sau khi hoàn tất chuẩn bị rejoin. Apply StatefulSet ở thời điểm này để lưu desired replicas 0 và liên kết tới PVC mới trước khi bật lại agent.

Trên Git Bash của laptop, chuyển manifest lên EC2.

```bash
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/database/postgres-aws.yaml \
  ubuntu@175.41.152.242:/home/ubuntu/postgres-aws.yaml
```

Trong phiên SSH AWS, apply rồi kiểm tra số replica mong muốn của cả database và ứng dụng.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-aws.yaml

sudo k3s kubectl -n issues get statefulset/postgres deployment/issues-app \
  -o 'custom-columns=KIND:.kind,NAME:.metadata.name,DESIRED:.spec.replicas'
```

Kết quả cần có DESIRED bằng 0 cho cả postgres và issues-app. StatefulSet lấy giá trị này từ manifest vừa apply. Deployment ứng dụng lấy giá trị đã scale ở bước 4.26.

Kiểm tra PVC mà StatefulSet sẽ sử dụng và các Pod object còn lưu trong API.

```bash
sudo k3s kubectl -n issues get statefulset postgres \
  -o jsonpath='{.spec.template.spec.volumes[?(@.name=="data")].persistentVolumeClaim.claimName}{"\n"}'

sudo k3s kubectl -n issues get pods -o wide
```

Tên PVC cần là postgres-data-rejoin-aws-01. Pod object cũ có thể còn xuất hiện hoặc ở trạng thái Terminating khi kubelet đang tắt. Danh sách này giúp xác định các object cần xử lý trước lúc bật lại agent. Đối chiếu với phép kiểm tra socket PostgreSQL đã dừng ở bước 4.25 để phân biệt trạng thái lưu trong API với process trên host.

Checkpoint của bước này gồm desired replicas của hai workload bằng 0, StatefulSet tham chiếu PVC mới và danh sách Pod object hiện tại để chuẩn bị bước tiếp theo.

### 4.34. Xử lý Pod object cũ khi agent AWS đang tắt

Trong lượt thực hành, postgres-0 và issues-app-f8fb495f5-thvkw đang Terminating. Kubelet đang tắt trong chế độ agentless nên chưa thể hoàn tất quy trình xóa Pod thông thường. Cột READY có thể vẫn chứa trạng thái được báo trước đó.

Trên SSH AWS, kiểm tra desired replicas và process PostgreSQL trước khi xóa object.

```bash
sudo k3s kubectl -n issues get statefulset/postgres deployment/issues-app \
  -o 'custom-columns=KIND:.kind,NAME:.metadata.name,DESIRED:.spec.replicas'

sudo pgrep -a -x postgres
sudo ss -ltnp 'sport = :5432'
```

Điều kiện tiếp tục là hai workload đều DESIRED 0, pgrep không tìm thấy process postgres và ss chỉ hiện tiêu đề bảng. Control plane AWS vẫn chạy agentless theo bước 4.25. Nếu kết quả khác các điều kiện này, cần xác định nguyên nhân trước khi thực hiện lệnh xóa.

Với các điều kiện trên đã đạt, xóa đích danh hai Pod object cũ của lượt thực hành.

```bash
sudo k3s kubectl -n issues delete pod \
  postgres-0 issues-app-f8fb495f5-thvkw \
  --force --grace-period=0 --ignore-not-found
```

--force --grace-period=0 yêu cầu API xóa object ngay. --ignore-not-found cho phép chạy lại nếu một object đã được xóa. Cơ chế force delete có thể hoàn tất trước khi process trên node kết thúc, nên việc xác nhận process đã dừng và agent đang tắt là điều kiện cần cho thao tác ở bước này. [Kubernetes force delete StatefulSet Pods](https://kubernetes.io/docs/tasks/run-application/force-delete-stateful-set-pod/).

Kiểm tra kết quả và tình trạng PVC.

```bash
sudo k3s kubectl -n issues get pods -o wide
sudo k3s kubectl -n issues get pvc postgres-data postgres-data-rejoin-aws-01
```

Hai Pod object vừa xóa cần biến mất. PVC postgres-data vẫn Bound và PVC postgres-data-rejoin-aws-01 dự kiến Pending cho tới khi Job clone được lên lịch. Bước tiếp theo khôi phục agent để có thể chạy Job clone dữ liệu từ Azure.

### 4.35. Khôi phục agent AWS sau khi chuẩn bị workload

Agent cung cấp kubelet và container runtime để node chạy Pod. Sau khi desired replicas của hai workload bằng 0, StatefulSet trỏ PVC mới và các Pod object cũ đã được xóa, khôi phục agent để có thể chạy Job clone. Azure tiếp tục giữ vai trò writer trong bước này.

Trên SSH AWS, đối chiếu trạng thái trước khi khởi động lại K3s.

```bash
sudo k3s kubectl -n issues get statefulset/postgres deployment/issues-app \
  -o 'custom-columns=KIND:.kind,NAME:.metadata.name,DESIRED:.spec.replicas'
sudo k3s kubectl -n issues get pods -o wide
sudo test -f /run/issues-k3s-start-approved && echo 'Boot approval present'
```

Hai workload cần DESIRED 0, hai Pod cũ đã biến mất và marker phê duyệt boot hiện tại còn tồn tại. Nếu một điều kiện chưa đạt, hoàn tất bước chuẩn bị tương ứng trước khi khởi động lại dịch vụ.

Khi các điều kiện đã đạt, chạy chuỗi lệnh sau.

```bash
sudo systemctl stop k3s &&
sudo rm -- /etc/rancher/k3s/config.yaml.d/99-rejoin.yaml &&
sudo systemctl start k3s
```

File 99-rejoin.yaml được tạo riêng ở bước 4.25 với disable-agent: true. Xóa file cấu hình tạm này rồi khởi động K3s sẽ khôi phục agent theo cấu hình thông thường của server. K3s đọc các file config.yaml.d/*.yaml khi khởi động. Dấu && khiến lệnh tiếp theo chỉ chạy khi lệnh trước thành công. Marker trong /run đã được phê duyệt cho boot hiện tại và được ExecStartPre kiểm tra khi start dịch vụ. [K3s configuration file](https://docs.k3s.io/installation/configuration#configuration-file).

Chờ node sẵn sàng rồi kiểm tra workload cùng cổng PostgreSQL.

```bash
sudo k3s kubectl wait --for=condition=Ready \
  node/mcf-aws-primary --timeout=180s

sudo k3s kubectl get nodes -o wide
sudo k3s kubectl -n issues get pods -o wide
sudo ss -ltnp 'sport = :5432'
```

Node cần Ready, hai workload ứng dụng và database vẫn có desired replicas 0, cổng 5432 chưa có listener. Các Pod hệ thống có thể được khôi phục trong quá trình node trở lại. Bước kế tiếp mới apply Job clone để thời hạn chạy của Job bắt đầu khi node đã có khả năng thực thi Pod.

### 4.36. Chạy Job clone Azure sang PVC rejoin trên AWS

Sau khi AWS node Ready, namespace issues đã hết Pod và cổng 5432 chưa có listener, chuyển manifest Job đã chuẩn bị lên EC2. Thực hiện trên Git Bash của laptop.

```bash
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/database/postgres-clone-rejoin-aws.yaml \
  ubuntu@175.41.152.242:/home/ubuntu/postgres-clone-rejoin-aws.yaml
```

Trong SSH AWS, kiểm tra peer WireGuard và writer Azure.

```bash
ping -c 2 -W 2 10.200.29.2
curl -fsS --max-time 10 -w '\n' \
  https://azure.mcf.todicode.tech/health/database
```

Ping cần nhận được phản hồi từ peer. Writer health cần trả role primary và writable true. Khi cả hai đạt, apply Job.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-clone-rejoin-aws.yaml

sudo k3s kubectl -n issues wait --for=condition=complete \
  job/postgres-clone-rejoin-aws-01 --timeout=600s
```

Job tạo Pod sử dụng network của host AWS để kết nối 10.200.29.2:5432 qua WireGuard. Script lấy credential từ Secret postgres-replication và chạy pg_basebackup vào PVC postgres-data-rejoin-aws-01. local-path provisioner cấp volume khi Pod được lên lịch, phù hợp WaitForFirstConsumer.

pg_basebackup sao chép dữ liệu của PostgreSQL cluster Azure. Tham số -X stream đưa WAL cần cho bản backup vào dữ liệu được nhận, còn -R tạo standby.signal và lưu thông tin kết nối phục vụ replication. Sau các kiểm tra cuối, script tạo marker .clone-complete. [PostgreSQL pg_basebackup](https://www.postgresql.org/docs/17/app-pgbasebackup.html).

Lệnh wait theo dõi condition Complete của Job. Job đã có activeDeadlineSeconds 600 và backoffLimit 0. Khi wait báo lỗi, cần đọc trạng thái và log để xác định nguyên nhân trước khi xử lý dữ liệu clone.

```bash
sudo k3s kubectl -n issues logs job/postgres-clone-rejoin-aws-01
sudo k3s kubectl -n issues get job postgres-clone-rejoin-aws-01
sudo k3s kubectl -n issues get pvc postgres-data-rejoin-aws-01
```

Kết quả nghiệm thu cần có log Base backup completed, Job Complete với COMPLETIONS 1/1 và PVC Bound. PostgreSQL StatefulSet AWS vẫn replicas 0 trong bước này. Sau khi bản clone được nghiệm thu, bước tiếp theo khởi động PostgreSQL AWS từ PVC mới và kiểm chứng vai trò standby.

### 4.37. Khởi động PostgreSQL AWS từ bản clone mới

Sau khi Job clone Complete 1/1, log có Base backup completed và PVC rejoin Bound, tăng số replica PostgreSQL AWS để khởi động database từ dữ liệu vừa nhận. Trong lượt thực hành, PVC mới được gắn với PV pvc-8f0f13b6-05b8-43d8-8887-fb30a9525613.

Trên laptop, mở deploy/kubernetes/database/postgres-aws.yaml và đổi spec.replicas từ 0 thành 1.

```yaml
spec:
  serviceName: postgres-headless
  replicas: 1
```

Thao tác này cập nhật desired state trong file quản lý StatefulSet. Volume data của manifest cần tiếp tục tham chiếu postgres-data-rejoin-aws-01 và command kiểm tra .clone-complete cùng PG_VERSION đã được chuẩn bị ở bước 4.32.

Trên Git Bash laptop, chuyển manifest đã chỉnh lên EC2.

```bash
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/database/postgres-aws.yaml \
  ubuntu@175.41.152.242:/home/ubuntu/postgres-aws.yaml
```

Trong SSH AWS, apply và chờ StatefulSet sẵn sàng.

```bash
sudo k3s kubectl apply -f /home/ubuntu/postgres-aws.yaml

sudo k3s kubectl -n issues rollout status statefulset/postgres --timeout=180s

sudo k3s kubectl -n issues get pod postgres-0 -o wide
```

StatefulSet tạo Pod postgres-0 và mount PVC rejoin. Command kiểm tra bản clone trước khi gọi entrypoint. PostgreSQL đọc standby.signal cùng cấu hình kết nối do pg_basebackup -R tạo để khởi động recovery và nhận WAL từ Azure. [PostgreSQL pg_basebackup](https://www.postgresql.org/docs/17/app-pgbasebackup.html).

Khi Pod đạt 1/1 Running, kiểm tra vai trò và WAL receiver bằng kết nối SQL trên AWS.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT pg_is_in_recovery() AS in_recovery,
          current_setting('transaction_read_only') AS read_only;
   SELECT status, sender_host, sender_port,
          pg_last_wal_receive_lsn() AS receive_lsn,
          pg_last_wal_replay_lsn() AS replay_lsn
   FROM pg_stat_wal_receiver;"
```

Kết quả cần có in_recovery t, read_only on và một dòng receiver status streaming, sender_host 10.200.29.2, sender_port 5432. in_recovery xác nhận vai trò standby, transaction_read_only xác nhận chế độ chỉ đọc của kết nối và receiver cho biết nguồn WAL Azure. LSN cho biết tiến độ nhận và replay tại thời điểm truy vấn. Sau bước này cần đối chiếu sender trên Azure và dữ liệu đã ghi sau failover trước khi nghiệm thu rejoin.

### 4.38. Đối chiếu WAL sender Azure và dữ liệu sau failover trên AWS

Kết quả kiểm tra AWS sau khi khởi động từ PVC rejoin đã có in_recovery t, read_only on và receiver streaming từ 10.200.29.2:5432. receive_lsn cùng replay_lsn đạt 0/5000060 tại thời điểm truy vấn. Tiếp tục kiểm tra kết nối từ phía Azure và đọc lại dữ liệu đã tạo sau failover.

Trên SSH Azure, xem WAL sender.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT application_name, client_addr, state, sync_state,
          sent_lsn, write_lsn, flush_lsn, replay_lsn
   FROM pg_stat_replication;"
```

Kết nối AWS cần có application_name mcf-aws-standby, client_addr 10.200.29.1, state streaming và sync_state async. application_name đến từ cấu hình kết nối mà Job clone lưu qua pg_basebackup -R. client_addr đối chiếu địa chỉ WireGuard của bên nhận. View pg_stat_replication cung cấp trạng thái sender và tiến độ WAL được standby báo về. [PostgreSQL statistics views](https://www.postgresql.org/docs/17/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW).

Trên SSH AWS, đọc bản ghi đã tạo qua API Azure sau failover ở bước 4.21.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT run_id, seq, environment, created_at
   FROM probe_pings
   WHERE run_id = 'stage7-failover-20261114T121609Z'
     AND seq = 1;"
```

Kết quả cần có một dòng với seq 1 và environment azure. Bản ghi này được tạo khi Azure đã là primary, sau khi AWS cũ bị dừng. Đọc được nó trên AWS xác nhận dữ liệu sau failover hiện có trong database AWS đã rejoin. Cột environment lưu nơi bản ghi được tạo, còn vai trò database hiện tại được kiểm chứng bằng pg_is_in_recovery ở bước 4.37.

Phép đọc này kiểm chứng dữ liệu từ bản clone và quá trình cập nhật đến thời điểm đọc. Bước tiếp theo dùng một transaction mới trên Azure sau rejoin để kiểm tra replication tiếp tục chuyển dữ liệu sang AWS.

### 4.39. Tạo transaction mới trên Azure sau khi AWS rejoin

AWS đã đọc được bản ghi stage7-failover-20261114T121609Z, seq 1, environment azure, created_at 2026-11-14 12:16:13.966852+00. Tiếp tục tạo dữ liệu mới sau thời điểm AWS đã trở lại standby để kiểm chứng replication đang hoạt động với transaction mới.

Trên SSH Azure, chạy lệnh sau.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "INSERT INTO probe_pings (run_id, seq, environment)
   VALUES ('stage7-after-rejoin-' || gen_random_uuid()::text, 1, 'azure')
   RETURNING run_id, seq, environment, created_at;"
```

Tiền tố stage7-after-rejoin- nhận diện phép thử. gen_random_uuid() tạo định danh mới cho mỗi lần chạy, phép || nối tiền tố với UUID và ::text chuyển UUID sang kiểu chuỗi. environment azure được ghi tường minh bởi câu SQL này. RETURNING hiển thị bản ghi vừa thêm để lấy chính xác run_id cho phép đọc trên AWS ở bước tiếp theo. Với phiên psql đang dùng, transaction được commit khi câu lệnh thành công.

Giữ lại run_id cùng seq 1. Kết quả cần có một dòng RETURNING và thông báo INSERT 0 1. Để hoàn tất đối chiếu từ phía sender, cần lưu cả kết quả pg_stat_replication trên Azure theo bước 4.38.

### 4.40. Đọc transaction mới trên AWS sau rejoin

Lệnh ghi ở bước 4.39 đã tạo run_id stage7-after-rejoin-b7b94038-bdcc-4640-8d7d-7eba71d7336c, seq 1, environment azure, created_at 2026-11-14 15:14:23.426045+00 và trả INSERT 0 1.

Trên SSH AWS, đọc đúng bản ghi vừa tạo trên Azure.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT run_id, seq, environment, created_at
   FROM probe_pings
   WHERE run_id = 'stage7-after-rejoin-b7b94038-bdcc-4640-8d7d-7eba71d7336c'
     AND seq = 1;"
```

Kết quả cần có một dòng khớp cả run_id, seq, environment và created_at của lệnh ghi trên Azure. Bản ghi được tạo sau khi clone hoàn tất và AWS đã khởi động thành standby. Đọc được bản ghi này trên AWS kiểm chứng transaction mới đã được chuyển qua replication và replay thành dữ liệu có thể truy vấn.

Nếu lần đọc đầu trả 0 rows, chạy lại câu SELECT để đối chiếu do replication đang dùng chế độ bất đồng bộ. Nếu vẫn thiếu bản ghi, kiểm tra lại WAL receiver và WAL sender theo các bước 4.37 và 4.38.

Các run_id trong phần kết quả ghi nhận lượt thực hành hiện tại. Khi thực hiện lại project, dùng run_id do câu INSERT của lượt mới trả về để đối chiếu.

### 4.41. Khôi phục ứng dụng AWS kết nối tới database standby

AWS đã đọc được transaction mới stage7-after-rejoin-b7b94038-bdcc-4640-8d7d-7eba71d7336c với seq 1, environment azure và created_at 2026-11-14 15:14:23.426045+00. Dữ liệu khớp lệnh ghi trên Azure sau khi AWS rejoin, kiểm chứng luồng replication đang chuyển transaction mới sang AWS.

Khôi phục Deployment ứng dụng AWS đã scale về 0 ở bước 4.26. Manifest deploy/kubernetes/app/app-deployment.yaml đang khai báo replicas 1 và image digest đã được kiểm chứng ở giai đoạn 5. Trên Git Bash laptop, chuyển manifest lên EC2.

```bash
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/app/app-deployment.yaml \
  ubuntu@175.41.152.242:/home/ubuntu/app-deployment.yaml
```

Trong SSH AWS, apply và chờ Deployment sẵn sàng.

```bash
sudo k3s kubectl apply -f /home/ubuntu/app-deployment.yaml
sudo k3s kubectl -n issues rollout status deployment/issues-app --timeout=180s
sudo k3s kubectl -n issues get pods -l app=issues-app -o wide
```

Deployment cần có Pod ứng dụng 1/1 Running. Ứng dụng lấy môi trường aws từ ConfigMap issues-app-config và kết nối Service postgres của cluster AWS. Service database ánh xạ tới PostgreSQL ở WireGuard 10.200.29.1. readinessProbe gọi /api/database/status, hỗ trợ database standby khi kết nối thành công.

Kiểm tra HTTPS origin AWS ngay trong SSH AWS.

```bash
curl -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://aws.mcf.todicode.tech/api/database/status

curl -sS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://aws.mcf.todicode.tech/health/database
```

Endpoint /api/database/status cần HTTP 200, connected true, role standby, writable false và replication_connected true. Endpoint /health/database cần HTTP 503 vì nó biểu diễn điều kiện writable primary mà Route 53 sử dụng. -f ở câu curl đầu làm lệnh thất bại khi gặp HTTP lỗi. Câu curl thứ hai dùng -sS để hiển thị cả body và HTTP 503 phục vụ đối chiếu vai trò standby.

Checkpoint này nghiệm thu ứng dụng AWS phục vụ được HTTP và truy vấn database standby sau rejoin. Cần lưu kết quả endpoint trước khi chuyển sang chuẩn bị failback có kiểm soát.

### 4.42. Đối chiếu primary Azure và kết nối AWS trước failback

Ứng dụng AWS sau rejoin đã trả /api/database/status HTTP 200 và /health/database HTTP 503, với connected true, role standby, writable false, replication_connected true. receive_lsn và replay_lsn cùng đạt 0/50006C8 tại thời điểm kiểm tra. Database cùng ứng dụng AWS đã hoạt động ở vai trò standby.

Failback đưa vai trò writer về AWS rồi xây dựng lại Azure thành standby. Trình tự dự kiến gồm tạm dừng ghi ứng dụng trên Azure, đợi AWS replay tới mốc WAL được ghi nhận sau khi dừng ghi, fence Azure, promote AWS và mở lại ghi trên AWS. Cờ writes_enabled được lưu trong dữ liệu PostgreSQL và được replicate, nên việc mở lại ghi trên writer mới cần thực hiện tường minh. Quá trình chuyển vai trò có khoảng gián đoạn ghi cần ghi nhận trong lượt thực hành.

Trước khi bắt đầu dừng ghi, đối chiếu topology từ phía Azure. Trên SSH Azure, chạy lệnh sau.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -U taskflow -d taskflow -P pager=off -c \
  "SELECT pg_is_in_recovery() AS in_recovery,
          current_setting('transaction_read_only') AS read_only,
          writes_enabled
   FROM app_control
   WHERE singleton = TRUE;
   SELECT application_name, client_addr, state, sync_state,
          sent_lsn, write_lsn, flush_lsn, replay_lsn
   FROM pg_stat_replication;"
```

Kết quả vai trò Azure cần in_recovery f, read_only off và writes_enabled t. Kết nối AWS cần application_name mcf-aws-standby, client_addr 10.200.29.1, state streaming và sync_state async. Các vị trí WAL giúp quan sát tiến độ từ phía sender tại thời điểm truy vấn.

Checkpoint này xác nhận primary hiện tại và đúng bên nhận replication trước khi thay đổi cờ ghi. Lệnh SQL của bước này chỉ đọc trạng thái. Sau khi kết quả được đối chiếu, hướng dẫn tiếp theo thực hiện write barrier bằng advisory lock (2900, 1) tương ứng database/control.py.

### 4.43. Tạm dừng ghi Azure và lấy mốc WAL cho failback

Kết quả preflight đã xác nhận Azure in_recovery f, read_only off, writes_enabled t. WAL sender tới mcf-aws-standby ở 10.200.29.1 đang streaming async, với sent_lsn, write_lsn, flush_lsn và replay_lsn cùng đạt 0/50006C8 tại thời điểm kiểm tra. Lượt AWS rejoin đã được kiểm chứng từ database, dữ liệu mới, ứng dụng và kết nối hai phía.

Bước này bắt đầu khoảng tạm dừng ghi ứng dụng để chuyển vai trò có kiểm soát. Trên SSH Azure, chạy toàn bộ lệnh sau trong cùng một phiên psql.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -v ON_ERROR_STOP=1 -U taskflow -d taskflow -P pager=off \
  -c "SET lock_timeout = '15s'; SET synchronous_commit = on;" \
  -c "SELECT pg_advisory_lock(2900, 1);" \
  -c "UPDATE app_control SET writes_enabled = FALSE WHERE singleton = TRUE RETURNING writes_enabled;" \
  -c "SELECT pg_current_wal_flush_lsn() AS target_lsn;" \
  -c "SELECT pg_advisory_unlock(2900, 1) AS unlocked;"
```

Ứng dụng lấy shared transaction advisory lock (2900, 1) trong database/control.py trước khi kiểm tra cờ ghi. Exclusive session lock ở lệnh trên đợi các transaction đang giữ shared lock hoàn tất và chặn các writer ứng dụng mới trong lúc thay đổi cờ. lock_timeout giới hạn thời gian đợi lock ở 15 giây. ON_ERROR_STOP dừng các lệnh tiếp theo khi có lỗi SQL.

Các tùy chọn -c chạy lần lượt trên cùng kết nối psql. UPDATE được commit trước câu SELECT lấy target_lsn, trong khi session advisory lock vẫn được giữ qua các transaction. synchronous_commit on yêu cầu WAL của commit được flush trước khi UPDATE trả thành công. target_lsn được lấy sau đó làm mốc WAL mà AWS cần replay tới. Khi unlock hoàn tất, các writer ứng dụng tiếp tục qua bước lấy shared lock rồi đọc writes_enabled false, nên trả lỗi tạm dừng ghi. Session lock cũng được giải phóng khi kết nối kết thúc. [PostgreSQL advisory locks](https://www.postgresql.org/docs/17/explicit-locking.html#ADVISORY-LOCKS).

Giá trị (2900, 1) là định danh lock do project chọn và dùng thống nhất giữa ứng dụng với thao tác điều phối. Cờ này điều khiển các đường ghi ứng dụng có gọi guard_write. Trong khoảng chuyển vai trò, các thao tác SQL quản trị cần được phối hợp với mốc WAL đã lấy.

Kết quả cần có writes_enabled f, UPDATE 1, một target_lsn và unlocked t. Giữ lại target_lsn để truy vấn trên AWS ở bước tiếp theo. Nếu có lỗi SQL, đối chiếu lỗi cùng trạng thái cờ ghi trước khi tiếp tục chuyển vai trò.

Khi Azure writes_enabled false, endpoint writer health Azure trả 503. AWS standby cũng trả 503. Sau khi cả hai health check được đánh giá unhealthy, Route 53 trả record PRIMARY AWS theo failover policy. DNS có thể chọn AWS trong lúc AWS vẫn là standby. [Route 53 health-check routing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/health-checks-how-route-53-chooses-records.html).

Checkpoint là ghi ứng dụng Azure đã tạm dừng và mốc WAL sau commit đã được ghi nhận. Bước tiếp theo kiểm tra AWS vẫn standby, đã replay tới mốc này và đã nhận cờ writes_enabled false trước khi fence Azure.

### 4.44. Kiểm tra AWS replay tới mốc dừng ghi Azure

Write barrier trên Azure đã trả writes_enabled f, UPDATE 1, target_lsn 0/5000798 và unlocked t. Đối chiếu mốc này trên AWS trước khi fence Azure.

Trên SSH AWS, chạy truy vấn sau.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -v ON_ERROR_STOP=1 -U taskflow -d taskflow -P pager=off -c \
  "SELECT pg_is_in_recovery() AS in_recovery,
          writes_enabled,
          pg_last_wal_replay_lsn() AS replay_lsn,
          pg_last_wal_replay_lsn() >= '0/5000798'::pg_lsn AS caught_up
   FROM app_control
   WHERE singleton = TRUE;"
```

Kết quả cần một dòng với in_recovery t, writes_enabled f và caught_up t. replay_lsn cần lớn hơn hoặc bằng 0/5000798. Kiểu pg_lsn cho phép so sánh vị trí WAL theo thứ tự PostgreSQL. Phép so sánh dùng >= vì standby có thể tiếp tục replay thêm WAL sau mốc đã ghi nhận.

in_recovery xác nhận AWS vẫn là standby. writes_enabled f xác nhận thay đổi cờ điều khiển đã xuất hiện trong dữ liệu có thể truy vấn trên AWS. caught_up t xác nhận WAL đã được replay tới mốc lấy sau khi commit thao tác tạm dừng ghi trên Azure. Truy vấn kiểm tra cả dữ liệu và tiến độ replay trước khi thay đổi trạng thái nguồn.

Nếu caught_up f, thực hiện lại truy vấn và kiểm tra replication khi cần. Điều kiện chuyển sang fence Azure là đủ cả ba giá trị in_recovery t, writes_enabled f, caught_up t. Khi thực hiện lại project, thay 0/5000798 bằng target_lsn của chính lượt dừng ghi mới.

Checkpoint tiếp theo là xác nhận VM Azure đã được fence ở cấp cloud trước khi promote AWS. Cờ ghi ứng dụng tiếp tục false qua giai đoạn này.

### 4.45. Fence VM Azure trước khi promote AWS

AWS đã trả in_recovery t, writes_enabled f, replay_lsn 0/50008D8 và caught_up t so với target_lsn 0/5000798. Bên nhận đã replay tới mốc được lấy sau commit tạm dừng ghi trên Azure.

Thực hiện fencing ở cấp cloud bằng cách deallocate VM Azure đang giữ vai trò primary. Trên Git Bash laptop, chạy lệnh sau.

```bash
az vm deallocate \
  --subscription 52341a4a-a86f-4780-82dc-879b500022d8 \
  --resource-group mcf-azure-rg \
  --name mcf-azure-standby
```

subscription chỉ định tài khoản triển khai, resource-group xác định nhóm tài nguyên và name chọn đúng VM của project. Tên tài nguyên vẫn là mcf-azure-standby dù database bên trong hiện là primary. Deallocate dừng VM và giải phóng phần cấp phát compute. Trong lượt failback, VM được dừng giúp cô lập PostgreSQL writer cũ trước khi promote AWS. [Azure CLI deallocate](https://learn.microsoft.com/en-us/cli/azure/vm?view=azure-cli-latest#az-vm-deallocate).

Sau khi lệnh hoàn tất, truy vấn power state từ Azure.

```bash
az vm get-instance-view \
  --subscription 52341a4a-a86f-4780-82dc-879b500022d8 \
  --resource-group mcf-azure-rg \
  --name mcf-azure-standby \
  --query "instanceView.statuses[?starts_with(code, 'PowerState/')].code | [0]" \
  --output tsv
```

Kết quả cần là PowerState/deallocated. Query lọc phần trạng thái nguồn điện trong instanceView, lấy trường code và phần tử đầu tiên. --output tsv in giá trị thuận tiện đối chiếu. SSH Azure sẽ mất kết nối khi VM được dừng. Bằng chứng fencing ở bước này là power state do Azure báo về. [Azure VM states](https://learn.microsoft.com/en-us/azure/virtual-machines/states-billing).

Chỉ sau khi xác nhận PowerState/deallocated mới chuyển sang promote AWS. Startup guard đã cài trên Azure sẽ yêu cầu phê duyệt boot khi VM được khởi động lại để rejoin.

### 4.46. Promote PostgreSQL AWS sau khi fence Azure

Azure đã báo PowerState/deallocated qua instance view. AWS đã replay vượt target_lsn 0/5000798 và nhận writes_enabled false ở bước 4.44. Với nguồn writer cũ đã được fence, promote PostgreSQL AWS.

Trên SSH AWS, chạy lệnh sau.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -v ON_ERROR_STOP=1 -U taskflow -d taskflow -P pager=off -c \
  "SELECT pg_promote(true, 60) AS promoted;"
```

pg_promote yêu cầu PostgreSQL kết thúc recovery và chuyển thành primary. Đối số true yêu cầu chờ hoàn tất, 60 là số giây chờ tối đa. Kết quả promoted t xác nhận promotion hoàn tất trong thời gian chờ. Nếu hàm trả f hoặc lệnh có lỗi, đối chiếu trạng thái recovery và log trước khi mở ghi. [PostgreSQL recovery control functions](https://www.postgresql.org/docs/17/functions-admin.html#FUNCTIONS-RECOVERY-CONTROL).

Sau đó dùng kết nối psql mới để kiểm tra vai trò cùng cờ ứng dụng.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -v ON_ERROR_STOP=1 -U taskflow -d taskflow -P pager=off -c \
  "SELECT pg_is_in_recovery() AS in_recovery,
          current_setting('transaction_read_only') AS read_only,
          writes_enabled
   FROM app_control
   WHERE singleton = TRUE;"
```

Kết quả cần in_recovery f, read_only off và writes_enabled f. Hai cột đầu xác nhận PostgreSQL AWS đã là primary và kết nối có thể thực hiện transaction ghi. writes_enabled f tiếp tục giữ ứng dụng ở trạng thái tạm dừng ghi theo cờ đã replicate từ Azure. Theo database/role.py, writer health ở thời điểm này vẫn trả HTTP 503 vì cờ ứng dụng còn false.

Checkpoint là AWS được promote thành primary trong khi cờ ghi ứng dụng tiếp tục false. Bước kế tiếp mở ghi trên AWS sau khi đối chiếu kết quả promotion và vai trò.

### 4.47. Mở ghi ứng dụng trên primary AWS và kiểm tra writer health

Truy vấn trên AWS sau promotion đã xác nhận in_recovery f, read_only off và writes_enabled f. Azure đã được xác nhận PowerState/deallocated ở bước 4.45. Mở cờ ghi trên primary AWS bằng cùng cơ chế advisory lock mà ứng dụng sử dụng.

Trên SSH AWS, chạy toàn bộ khối lệnh sau.

```bash
sudo k3s kubectl -n issues exec postgres-0 -- \
  psql -X -v ON_ERROR_STOP=1 -U taskflow -d taskflow -P pager=off \
  -c "SET lock_timeout = '15s'; SET synchronous_commit = on;" \
  -c "SELECT pg_advisory_lock(2900, 1);" \
  -c "UPDATE app_control SET writes_enabled = TRUE WHERE singleton = TRUE RETURNING writes_enabled;" \
  -c "SELECT pg_advisory_unlock(2900, 1) AS unlocked;"
```

Exclusive session lock phối hợp thay đổi cờ với shared transaction lock của các đường ghi ứng dụng trong database/control.py. UPDATE được commit trước khi câu lệnh unlock chạy. Kết quả cần writes_enabled t, UPDATE 1 và unlocked t. Khi lock được nhả, request ứng dụng đọc được cờ true và có thể ghi vào primary AWS. lock_timeout giới hạn thời gian chờ lock, ON_ERROR_STOP dừng các lệnh tiếp theo khi có lỗi SQL và synchronous_commit on yêu cầu flush WAL của commit trước khi báo thành công.

Trong SSH AWS, kiểm tra writer health qua HTTPS origin.

```bash
curl -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://aws.mcf.todicode.tech/health/database
```

Kết quả cần HTTP 200, connected true, role primary, writable true và writes_paused false. database/role.py tính writable từ vai trò PostgreSQL, transaction_read_only và cờ writes_enabled. Kết quả này kiểm chứng ứng dụng AWS đã nhận trạng thái primary được phép ghi. Bước tiếp theo đối chiếu DNS, môi trường phục vụ hostname chung và một request ghi đọc qua API sau failback.

### 4.48. Kiểm tra DNS và HTTPS hostname chung sau khi mở ghi AWS

AWS đã trả writes_enabled t, UPDATE 1 và unlocked t. HTTPS writer health của origin AWS đã trả HTTP 200 với connected true, role primary, writable true, writes_paused false và current_lsn 0/5000B40. Tiếp tục nghiệm thu đường truy cập hostname chung từ laptop.

Trên Git Bash laptop, kiểm tra CNAME qua resolver công cộng.

```bash
nslookup -type=CNAME app.mcf.todicode.tech 1.1.1.1
```

CNAME cần trỏ aws.mcf.todicode.tech. Truy vấn này đối chiếu câu trả lời DNS của resolver 1.1.1.1. Cấu hình failover.tf chọn AWS là PRIMARY và Azure là SECONDARY, với TTL 30 giây cho record chung.

Kiểm tra môi trường phục vụ và writer health bằng hostname chung.

```bash
/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://app.mcf.todicode.tech/version

/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  https://app.mcf.todicode.tech/health/database
```

Endpoint /version cần HTTP 200 với environment aws, region ap-southeast-1 và commit_sha c56fd3f30baee50fa779607dc0fb1a2133b53a9d tương ứng image đang chạy. Endpoint /health/database cần HTTP 200 với role primary, writable true và writes_paused false. curl sử dụng cơ chế phân giải tên của máy laptop, nên kết quả HTTP kiểm chứng cả đường truy cập thực tế cùng TLS của hostname chung, bổ sung cho phép kiểm tra DNS qua resolver công cộng.

Nếu DNS hoặc HTTP chưa chuyển về kết quả mong đợi, đối chiếu lại sau khi health check và cache DNS được cập nhật. Khi cả hai origin đều bị đánh giá unhealthy, Route 53 vẫn có thể trả record PRIMARY AWS theo cơ chế đã giải thích ở bước 4.43, nên CNAME cần được đối chiếu cùng kết quả writer health.

Checkpoint là hostname chung phục vụ ứng dụng AWS với writer health 200. Bước tiếp theo kiểm tra ghi và đọc qua API hostname chung sau failback, rồi chuẩn bị rejoin Azure để khôi phục standby.

### 4.49. Ghi và đọc qua API hostname chung sau failback về AWS

HTTPS hostname chung đã trả /version HTTP 200 với environment aws, region ap-southeast-1 và commit_sha c56fd3f30baee50fa779607dc0fb1a2133b53a9d tại 2026-11-14T15:45:55.047567+00:00. Writer health cùng hostname đã trả HTTP 200, role primary, writable true và writes_paused false. Tiếp tục tạo dữ liệu qua API để kiểm chứng đường ghi sau chuyển vai trò.

Trên Git Bash laptop, tạo mã lượt thử và gửi POST.

```bash
MCF_FAILBACK_RUN_ID="stage7-failback-$(date -u +%Y%m%dT%H%M%SZ)"

printf '{"run_id":"%s","seq":1}\n' "$MCF_FAILBACK_RUN_ID" |
  /c/Windows/System32/curl.exe -fsS --max-time 10 \
    -H 'Content-Type: application/json' \
    --data-binary @- \
    -w '\nHTTP %{http_code}\n' \
    https://app.mcf.todicode.tech/api/ping
```

MCF_FAILBACK_RUN_ID giữ mã lượt thử trong terminal hiện tại. date -u dùng thời gian UTC để tạo hậu tố nhận diện. printf tạo JSON chứa run_id cùng seq 1, pipe truyền JSON vào stdin của curl và --data-binary @- gửi nội dung đó làm POST body. Header Content-Type khai báo JSON. Kết quả cần HTTP 200, run_id khớp biến vừa tạo, seq 1 và environment aws.

Trong cùng terminal Git Bash, đọc lại bằng API.

```bash
/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\nHTTP %{http_code}\n' \
  "https://app.mcf.todicode.tech/api/ping/$MCF_FAILBACK_RUN_ID"
```

GET cần HTTP 200 với run_id khớp, count 1 và pings chứa seq 1, environment aws. POST kiểm chứng ứng dụng cho phép ghi trên writer AWS, còn GET kiểm chứng bản ghi có thể đọc lại qua hostname chung sau commit. Giữ run_id để đối chiếu trên Azure sau khi rebuild standby.

Checkpoint là đường ứng dụng qua hostname chung đã ghi và đọc được trên AWS sau failback. Việc khôi phục topology hai cloud còn cần rejoin Azure thành standby từ dữ liệu primary AWS.

### 4.50. Bật Azure và kiểm tra startup guard trước rejoin

Hostname chung đã ghi và đọc thành công trên AWS với run_id stage7-failback-20261114T154715Z, seq 1, environment aws. POST cùng GET đều trả HTTP 200, GET có count 1. Giữ mã này để kiểm tra dữ liệu trên Azure sau khi rebuild standby.

AWS hiện là primary phục vụ ứng dụng. Azure cần được xây dựng lại thành standby từ dữ liệu primary AWS. Trước tiên bật VM Azure và kiểm tra guard của boot mới đang chặn PostgreSQL cũ.

Trên Git Bash laptop, bật đúng VM trong subscription project.

```bash
az vm start \
  --subscription 52341a4a-a86f-4780-82dc-879b500022d8 \
  --resource-group mcf-azure-rg \
  --name mcf-azure-standby

az vm get-instance-view \
  --subscription 52341a4a-a86f-4780-82dc-879b500022d8 \
  --resource-group mcf-azure-rg \
  --name mcf-azure-standby \
  --query "instanceView.statuses[?starts_with(code, 'PowerState/')].code | [0]" \
  --output tsv
```

Sau khi power state là PowerState/running, kết nối SSH từ laptop.

```bash
ssh -i ~/.ssh/mcf-lab azureuser@4.145.30.250
```

Trong SSH Azure, kiểm tra marker, dịch vụ và socket PostgreSQL.

```bash
sudo test -f /run/issues-k3s-start-approved
echo $?

sudo systemctl status k3s --no-pager --full
sudo ss -ltnp 'sport = :5432'
```

Phép test cần trả exit code 1 vì marker của boot trước đã mất. Dịch vụ K3s có thể hiện activating (auto-restart) hoặc failed do ExecStartPre kiểm tra marker thất bại. ss cần chỉ hiện tiêu đề bảng, thể hiện cổng 5432 chưa có listener. Startup guard kiểm soát thời điểm cho phép K3s khởi động, giúp chuẩn bị lại workload và PVC trước khi chạy database Azure.

Checkpoint của bước này là host Azure đã bật, marker phê duyệt boot còn thiếu và PostgreSQL cũ tiếp tục dừng. Bước kế tiếp cài cấu hình agentless tạm thời trên Azure trước khi tạo marker phê duyệt, tương tự quy trình AWS ở bước 4.24 và 4.25.

### 4.51. Khởi động control plane Azure ở chế độ agentless

Azure sau khi bật lại đã xác nhận marker phê duyệt boot còn thiếu, ExecStartPre kiểm tra marker thất bại và cổng 5432 chưa có listener. Chuẩn bị control plane agentless để cập nhật trạng thái workload trước khi khôi phục khả năng chạy Pod.

Sử dụng lại file deploy/k3s/rejoin-control-plane.yaml đã chuẩn bị cho AWS ở bước 4.24, với nội dung disable-agent: true. Trên Git Bash laptop, chuyển file lên Azure.

```bash
scp -i ~/.ssh/mcf-lab \
  deploy/k3s/rejoin-control-plane.yaml \
  azureuser@4.145.30.250:/home/azureuser/rejoin-control-plane.yaml
```

Trong SSH Azure, dừng vòng khởi động lại K3s và cài cấu hình tạm.

```bash
sudo systemctl stop k3s &&
sudo install -d -m 700 -o root -g root /etc/rancher/k3s/config.yaml.d &&
sudo install -m 600 -o root -g root \
  /home/azureuser/rejoin-control-plane.yaml \
  /etc/rancher/k3s/config.yaml.d/99-rejoin.yaml

sudo cat /etc/rancher/k3s/config.yaml.d/99-rejoin.yaml
```

Nội dung cần là disable-agent: true. install tạo thư mục và sao chép file với quyền sở hữu root cùng permission chỉ định. Dấu && yêu cầu thao tác trước thành công để thực hiện thao tác tiếp theo. K3s đọc drop-in này khi khởi động.

Sau khi xác nhận nội dung cấu hình, tạo marker phê duyệt boot hiện tại và khởi động K3s.

```bash
sudo touch /run/issues-k3s-start-approved &&
sudo systemctl reset-failed k3s &&
sudo systemctl start k3s
```

Marker cho phép vượt qua kiểm tra ExecStartPre. disable-agent true khiến server chạy control plane với kubelet, containerd và CNI của agent được tắt. Chế độ agentless được K3s đánh dấu experimental và được dùng tạm trong quy trình rejoin này. [K3s agentless servers](https://docs.k3s.io/advanced#running-agentless-servers-experimental).

Kiểm tra API server và socket PostgreSQL.

```bash
sudo k3s kubectl get --raw=/readyz
sudo ss -ltnp 'sport = :5432'
```

API cần trả ok, socket 5432 tiếp tục chỉ có tiêu đề bảng. Nếu API đang khởi tạo, kiểm tra lại readyz sau khi chờ vài giây. Các Pod object từ boot trước có thể còn lưu trong API với trạng thái cũ. Bước tiếp theo đặt desired replicas của PostgreSQL và ứng dụng Azure về 0 để chuẩn bị PVC và clone mới.

### 4.52. Đặt workload Azure về 0 trong chế độ agentless

Thực hiện khi API Azure ở bước 4.51 đã trả readyz ok và cổng 5432 chưa có listener. Đặt desired replicas của StatefulSet PostgreSQL và Deployment ứng dụng về 0 để chuẩn bị thay đổi PVC trước khi khôi phục agent.

Trong SSH Azure, chạy lần lượt hai lệnh scale.

```bash
sudo k3s kubectl -n issues scale statefulset/postgres --replicas=0
sudo k3s kubectl -n issues scale deployment/issues-app --replicas=0
```

scale cập nhật spec.replicas của resource đang lưu trong API. StatefulSet quản lý database và Deployment quản lý ứng dụng web. Giá trị 0 yêu cầu controller duy trì số Pod của hai workload bằng 0. Các manifest trên laptop được cập nhật hoặc apply lại theo trạng thái phù hợp trong các bước tiếp theo.

Kiểm tra desired state cùng các Pod object hiện tại.

```bash
sudo k3s kubectl -n issues get statefulset/postgres deployment/issues-app \
  -o 'custom-columns=KIND:.kind,NAME:.metadata.name,DESIRED:.spec.replicas'

sudo k3s kubectl -n issues get pods -o wide
```

Cả postgres và issues-app cần DESIRED 0. Pod object cũ có thể tiếp tục hiện Terminating vì kubelet đang tắt. Danh sách này được dùng để đối chiếu trước bước xử lý object cũ và bật lại agent.

Checkpoint của bước này là desired replicas của hai workload Azure bằng 0 và đã ghi nhận danh sách Pod object còn lưu trong API. Bước tiếp theo chuẩn bị PVC mới dành cho bản clone từ AWS.

### 4.53. Tạo PVC mới cho Azure rejoin

Azure đã xác nhận StatefulSet postgres và Deployment issues-app đều DESIRED 0. Pod postgres-0 và issues-app-f8fb495f5-lf458 đang Terminating. Chuẩn bị PVC riêng cho dữ liệu clone từ primary AWS trước khi xử lý Pod object cũ và khôi phục agent.

Trên laptop, tạo file deploy/kubernetes/database/postgres-pvc-rejoin-azure.yaml với nội dung sau.

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data-rejoin-azure-01
  namespace: issues
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path-retain
  resources:
    requests:
      storage: 5Gi
```

PVC này dành cho lượt rebuild Azure đầu tiên, với tên riêng để Job clone cùng StatefulSet tham chiếu ở các bước tiếp theo. ReadWriteOnce cho phép volume được mount đọc ghi trên một node. StorageClass local-path-retain đã được chuẩn bị với reclaimPolicy Retain và volumeBindingMode WaitForFirstConsumer. Request 5Gi khai báo nhu cầu lưu trữ, còn dung lượng thực tế của local-path vẫn phụ thuộc filesystem trên host.

Trên Git Bash laptop, chuyển manifest lên Azure.

```bash
scp -i ~/.ssh/mcf-lab \
  deploy/kubernetes/database/postgres-pvc-rejoin-azure.yaml \
  azureuser@4.145.30.250:/home/azureuser/postgres-pvc-rejoin-azure.yaml
```

Trong SSH Azure, apply rồi kiểm tra PVC cùng dung lượng host.

```bash
sudo k3s kubectl apply -f /home/azureuser/postgres-pvc-rejoin-azure.yaml

sudo k3s kubectl -n issues get pvc postgres-data postgres-data-rejoin-azure-01

sudo df -h /var/lib/rancher/k3s/storage
sudo du -sh /var/lib/rancher/k3s/storage
```

PVC cũ postgres-data cần tiếp tục Bound. PVC mới dự kiến Pending do WaitForFirstConsumer, chờ Pod clone được lên lịch sau khi agent khôi phục. df hiển thị dung lượng trống filesystem, du cho biết dữ liệu local-path hiện chiếm bao nhiêu trên host. Hai kết quả được dùng để đối chiếu khả năng giữ bản cũ cùng bản clone mới trên OS disk Azure.

Checkpoint là PVC mới đã được tạo và đã đối chiếu dung lượng trống cho bản clone. Bước tiếp theo chuẩn bị Job clone AWS sang PVC Azure mới cùng cấu hình StatefulSet Azure dùng bản clone này.

## 5. Theo dõi tiến độ

- [x] Nghiệm thu giai đoạn 6 và xác định phạm vi giai đoạn 7.
- [x] Đối chiếu AWS account và EC2 của lượt thực hành.
- [x] Đối chiếu subscription và VM Azure của lượt thực hành.
- [x] Khởi động EC2 AWS và chờ status checks đạt.
- [x] Xác nhận Azure Running sau lệnh start.
- [ ] Kiểm tra dịch vụ, node và workload trên AWS sau khi bật máy.
- [x] Đối chiếu App Pod và PostgreSQL Pod AWS đạt 1/1 Running.
- [ ] Kiểm tra dịch vụ, node và workload trên Azure sau khi bật máy.
- [x] Đối chiếu App Pod và PostgreSQL Pod Azure đạt 1/1 Running.
- [x] Đối chiếu vai trò PostgreSQL AWS primary, Azure standby sau khi bật máy.
- [x] Đối chiếu WAL sender và receiver đều streaming qua đúng peer WireGuard.
- [x] Ghi bản ghi kiểm chứng mới trên AWS và đọc cùng bản ghi trên Azure.
- [x] Khởi động và kiểm tra topology AWS primary, Azure standby.
- [x] Viết systemd drop-in kiểm soát khởi động K3s.
- [x] Cài drop-in trên AWS và đối chiếu cấu hình, marker của boot hiện tại.
- [x] Cài drop-in trên Azure và đối chiếu cấu hình, marker của boot hiện tại.
- [x] Kiểm chứng marker mất và K3s bị chặn sau reboot Azure.
- [x] Khôi phục workload Azure sau khi phê duyệt boot trong phép thử guard.
- [x] Đối chiếu Azure standby và WAL streaming sau phép thử guard.
- [x] Kiểm chứng transaction mới và đối chiếu LSN sau khi receiver khởi động lại.
- [x] Chuẩn bị và kiểm tra cơ chế kiểm soát writer cũ khi khởi động lại.
- [x] Dừng EC2 AWS và xác nhận trạng thái Stopped trước promote.
- [x] Promote Azure và đối chiếu PostgreSQL primary cùng cờ cho phép ghi ứng dụng.
- [x] Kiểm tra writer health Azure, DNS và request qua hostname chung sau promote.
- [x] Đối chiếu DNS chọn Azure và hostname chung trả version của ứng dụng Azure.
- [x] Ghi và đọc lại bản ghi qua API hostname chung sau failover.
- [x] Đối chiếu bản ghi trước sự cố và writer health qua hostname chung.
- [x] Thực hành failover AWS sang Azure với fencing được xác nhận.
- [x] Kiểm tra truy cập và dữ liệu trên writer Azure.
- [x] Bật host AWS và xác nhận guard chặn K3s cùng PostgreSQL trước rejoin.
- [x] Chuẩn bị cấu hình K3s agentless phục vụ rejoin.
- [x] Khởi động control plane AWS với agent tắt và xác nhận PostgreSQL cũ tiếp tục dừng.
- [ ] Đặt desired replicas của PostgreSQL và ứng dụng AWS về 0 để chuẩn bị rejoin.
- [x] Chuẩn bị PVC mới cho lượt AWS rejoin đầu tiên.
- [x] Apply PVC mới trên AWS và đối chiếu PVC cũ cùng dung lượng filesystem.
- [x] Đối chiếu dung lượng filesystem AWS cho lượt clone mới.
- [x] Tạo Secret replication trên AWS từ credential hiện có và đối chiếu metadata.
- [x] Chuẩn bị script clone dùng chung với tên kết nối theo cloud và apply ConfigMap trên AWS.
- [x] Chuẩn bị manifest Job clone AWS rejoin từ Azure vào PVC mới.
- [x] Chuẩn bị StatefulSet AWS replicas 0, PVC mới và kiểm tra clone hoàn tất.
- [ ] Apply StatefulSet AWS và đối chiếu desired replicas, PVC cùng Pod object cũ.
- [x] Đối chiếu StatefulSet tham chiếu PVC rejoin và hai Pod object cũ đang Terminating.
- [ ] Xóa Pod object cũ sau khi xác nhận desired replicas 0 và PostgreSQL đã dừng.
- [x] Đối chiếu hai Pod object cũ đã biến mất khỏi namespace issues.
- [x] Khôi phục agent AWS, kiểm tra node Ready và PostgreSQL tiếp tục dừng trước clone.
- [x] Chạy Job clone từ Azure sang PVC rejoin AWS và đối chiếu log, Job, PVC.
- [x] Khởi động PostgreSQL AWS từ PVC rejoin và đối chiếu vai trò cùng WAL receiver.
- [x] Đối chiếu sender Azure của kết nối AWS standby.
- [x] Đọc bản ghi sau failover trên AWS đã rejoin.
- [x] Tạo transaction mới trên Azure sau khi AWS rejoin.
- [x] Tạo và đọc lại transaction mới từ Azure sang AWS sau rejoin.
- [x] Khôi phục ứng dụng AWS và đối chiếu readiness cùng writer health của standby.
- [x] Kiểm chứng database, dữ liệu mới và ứng dụng AWS hoạt động ở vai trò standby sau rejoin.
- [x] Đối chiếu primary Azure và WAL sender tới AWS trước failback.
- [x] Rejoin AWS thành standby.
- [x] Tạm dừng ghi Azure bằng write barrier và lấy mốc WAL sau commit.
- [x] Xác nhận AWS standby đã replay tới mốc dừng ghi và nhận writes_enabled false.
- [x] Deallocate VM Azure và xác nhận power state để fence writer cũ trước failback.
- [x] Đối chiếu AWS sau promotion là primary với cờ ghi ứng dụng còn false.
- [x] Mở ghi ứng dụng AWS và xác nhận writer health HTTP 200.
- [ ] Đối chiếu DNS và HTTPS hostname chung phục vụ primary AWS sau failback.
- [x] Đối chiếu HTTPS hostname chung trả version AWS và writer health HTTP 200 sau failback.
- [x] Ghi và đọc lại dữ liệu qua API hostname chung trên primary AWS sau failback.
- [x] Bật Azure và kiểm chứng startup guard chặn database cũ trước rejoin.
- [ ] Khởi động control plane Azure agentless và xác nhận PostgreSQL cũ tiếp tục dừng.
- [x] Đặt desired replicas PostgreSQL và ứng dụng Azure về 0 trước rejoin.
- [ ] Tạo PVC Azure rejoin và đối chiếu PVC cũ cùng dung lượng filesystem.
- [ ] Failback và khôi phục topology AWS primary, Azure standby.

## 6. Tài liệu kỹ thuật

- [PostgreSQL 17 failover](https://www.postgresql.org/docs/17/warm-standby-failover.html).
- [AWS CLI get-caller-identity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html).
- [AWS CLI describe-instances](https://docs.aws.amazon.com/cli/latest/reference/ec2/describe-instances.html).
- [AWS CLI start-instances](https://docs.aws.amazon.com/cli/latest/reference/ec2/start-instances.html).
- [AWS CLI instance-status-ok](https://docs.aws.amazon.com/cli/latest/reference/ec2/wait/instance-status-ok.html).
