# Giai đoạn 9 — Đo và so sánh failover

Thí nghiệm so sánh cùng ứng dụng ở hai cấu hình. Cấu hình A dùng AWS-only và khôi phục dịch vụ trên AWS. Cấu hình B dùng AWS primary và Azure warm standby để chuyển writer sang Azure khi EC2 dừng. Các chỉ số và nguyên tắc so sánh nằm trong [tiêu chí nghiệm thu](../PROJECT_REQUIREMENTS.md#4-baseline-và-nguyên-tắc-đo).

## Bước 1 — Đo hệ hai cloud ở trạng thái bình thường

Giữ AWS nhận ghi và Azure nhận WAL. Chạy probe từ laptop qua tên miền chung trong 120 giây, với chu kỳ mục tiêu 2 giây. Bước này kiểm tra được toàn bộ đường đọc và ghi trước khi gây lỗi ở các lượt sau.

```bash
mkdir -p experiments/runs
run_id="stage9-steady-$(date -u +%Y%m%dT%H%M%SZ)"

.venv/Scripts/python.exe -u scripts/probe_failover.py \
  --url https://app.mcf.todicode.tech \
  --interval 2 \
  --duration 120 \
  --timeout 3 \
  --fresh-connections \
  --run-id "$run_id" \
  --out "experiments/runs/$run_id.csv"
```

Mỗi lượt probe gọi `GET /version` và `POST /api/ping`. Kết nối mới được mở cho từng request. Cuối lượt đo, script đọc lại các bản ghi của `run_id` để kiểm tra những write đã được server xác nhận thành công. Lưu CSV và tóm tắt JSON trong `experiments/runs/`.

### Kết quả thực tế

Lượt `stage9-steady-20261120T094331Z` ghi 60 mẫu từ 09:43:31,966 đến 09:45:30,106 UTC ngày 20/11/2026. Tất cả request do AWS phục vụ thông qua tên miền chung.

| Thao tác | Thành công | Tỷ lệ lỗi | p50 | p95 | Khoảng gián đoạn |
|---|---:|---:|---:|---:|---|
| Đọc `GET /version` | 60/60 | 0% | 95 ms | 133 ms | Không quan sát thấy |
| Ghi `POST /api/ping` | 60/60 | 0% | 108 ms | 128 ms | Không quan sát thấy |

Đối chiếu cuối lượt cho thấy đủ 60/60 bản ghi đã được xác nhận thành công. Đây là mốc độ trễ khi cấu hình B đang vận hành bình thường. Thời gian phục hồi, gián đoạn khi có lỗi và dữ liệu còn lại sau chuyển writer sẽ được ghi nhận tại các lượt gây lỗi.

## Bước 2 — Kiểm tra bộ điều phối trước khi thử lỗi

Ở thư mục gốc repo trên laptop, lấy IP Azure rồi mở SSH.

```bash
azure_ip=$(terraform -chdir=deploy/terraform/azure output -raw azure_public_ip)
ssh -i ~/.ssh/mcf-lab "azureuser@$azure_ip"
```

Trên Azure, kiểm tra service, cờ cấu hình đã nạp và trạng thái lưu trên đĩa.

```bash
sudo systemctl is-active mcf-watcher
sudo journalctl -u mcf-watcher -b --grep='auto_failover=' -n 1 --no-pager
grep -m 1 '"phase"' "$HOME/.local/state/mcf-controller/state.json"
```

Kết quả ghi nhận là `active`, `auto_failover=True auto_recovery=True` và `"phase": "complete"`. Watcher đang chạy với cả hai chế độ tự động bật, và vòng khôi phục trước đã hoàn tất. Khi thử lỗi AWS, Azure và watcher tiếp tục chạy để thực hiện failover và khôi phục.

## Bước 3 — Đo failover trên hai cloud, lượt B01

Giữ topology AWS primary và Azure warm standby. Chạy probe qua tên miền chung từ Git Bash trên laptop. Chọn cửa sổ 20 phút và chu kỳ mục tiêu 2 giây.

```bash
mkdir -p experiments/runs
run_id="stage9-b01-$(date -u +%Y%m%dT%H%M%SZ)"

.venv/Scripts/python.exe -u scripts/probe_failover.py \
  --url https://app.mcf.todicode.tech \
  --interval 2 \
  --duration 1200 \
  --timeout 3 \
  --fresh-connections \
  --run-id "$run_id" \
  --out "experiments/runs/$run_id.csv"
```

Chờ khoảng một phút và xác nhận các mẫu gần nhất đều đọc, ghi thành công qua AWS. Từ Git Bash thứ hai tại thư mục gốc repo, nhập ID của lượt probe.

```bash
read -r -p 'Paste the run ID from Terminal 1: ' run_id
```

Lấy EC2 ID từ Terraform và gửi một yêu cầu dừng. File `.fault.log` lưu thời điểm UTC trước lệnh AWS CLI và kết quả API. Giữ Azure và watcher hoạt động để hoàn tất vòng khôi phục tự động.

```bash
aws_instance_id=$(terraform -chdir=deploy/terraform/aws output -raw aws_instance_id)
fault_log="experiments/runs/$run_id.fault.log"

if [[ "$run_id" =~ ^stage9-b01-[0-9]{8}T[0-9]{6}Z$ &&
      "$aws_instance_id" =~ ^i-[0-9a-f]+$ &&
      ! -e "$fault_log" ]]; then
  (
    set -o pipefail
    {
      printf 'stop_requested_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
      aws ec2 stop-instances \
        --profile default \
        --region ap-southeast-1 \
        --instance-ids "$aws_instance_id" \
        --query 'StoppingInstances[0].{instance:InstanceId,previous:PreviousState.Name,current:CurrentState.Name}' \
        --output json --no-cli-pager
    } 2>&1 | tee "$fault_log"
  )
else
  printf 'Check the run ID, EC2 instance ID, and fault log before retrying.\n' >&2
fi
```

### Kết quả phía client

Lượt `stage9-b01-20261120T190829Z` ghi 519 mẫu từ 19:08:30,261 đến 19:28:29,490 UTC ngày 20/11/2026. Mốc dừng là 19:10:00,264 UTC, khoảng 90 giây sau mẫu đầu. AWS trả trạng thái chuyển từ `running` sang `stopping`.

| Sự kiện | Giờ UTC | Bằng chứng |
|---|---|---|
| Gửi yêu cầu dừng EC2 | 19:10:00,264 | `.fault.log` |
| Mẫu đầu ghi thành công qua Azure | 19:14:03,577 | `seq=86`, `write_status=200`, `served_by=azure` |
| Mẫu đầu ghi thành công trở lại qua AWS | 19:20:34,375 | `seq=281`, `write_status=200`, `served_by=aws` |

Thời gian từ yêu cầu dừng tới mẫu ghi thành công đầu trên Azure là khoảng **243,3 giây**. Đây là mốc bắt đầu mẫu chứa POST thành công. Downtime của script đo từ mẫu thành công cuối trước chuỗi lỗi đến mẫu thành công đầu sau đó.

| Chỉ số | Đọc `GET /version` | Ghi `POST /api/ping` |
|---|---:|---:|
| Thành công | 444/519 | 437/519 |
| Tỷ lệ lỗi | 14,5% | 15,8% |
| p50 / p95 của request thành công | 97 / 142 ms | 111 / 132 ms |
| Gián đoạn failover | 243,1 s | 243,1 s |
| Gián đoạn failback | 72,1 s | 86,2 s |

AWS xác nhận 284 lượt ghi, Azure xác nhận 153 lượt. Đối chiếu cuối lượt tìm thấy đủ **437/437** bản ghi đã được xác nhận. Kết quả tính cho riêng B01 với lỗi dừng EC2 theo quy trình AWS. CSV, summary JSON và fault log được lưu trong `experiments/runs/`.

### Đối chiếu journal của watcher

Trên Azure, lọc journal theo cửa sổ UTC của B01 để giữ các mốc phát hiện lỗi, chuyển writer và khôi phục standby.

```bash
sudo journalctl -u mcf-watcher \
  --since '2026-11-20 19:09:55 UTC' \
  --until '2026-11-20 19:28:40 UTC' \
  --utc --no-hostname --output=short-iso-precise --no-pager \
  --grep='failover_candidate=True|recovery_phase=|failover_step=(fence_confirmed|promote_azure|promotion_confirmed|writer_confirmed)|failback_step=(azure_writes_paused|azure_postgres_fenced)|shared_writer='
```

Các mốc dưới đây thuộc cùng operation ID `fd573668ea714dba821dc2e3c6bea332`. Bản trích được lưu tại `experiments/runs/stage9-b01-20261120T190829Z.watcher.log`.

| Giờ UTC | Mốc watcher | Ý nghĩa |
|---|---|---|
| 19:12:07,448 | `failover_candidate=True` lần đầu | EC2 đã `stopped`, Route 53 báo AWS unhealthy và Azure còn standby |
| 19:12:30,557 | `recovery_phase=failover_pending` | Đã đủ ba lần kiểm tra liên tiếp để bắt đầu chuyển writer |
| 19:12:31,141 | `fence_confirmed`, `promote_azure` | Watcher kiểm chứng AWS đã dừng rồi yêu cầu promote Azure |
| 19:12:31,884 | `writer_confirmed` | Endpoint writer trực tiếp của Azure đã đạt kiểm tra |
| 19:14:12,849 | `shared_writer=azure` | Watcher ghi thành công qua tên miền chung, rồi bắt đầu rejoin AWS |
| 19:16:15,157 | `recovery_phase=wait_failback` | AWS đã trở lại dưới vai trò standby |
| 19:19:18,158 | `azure_writes_paused` | Azure tạm ngừng nhận ghi để chốt mốc WAL |
| 19:19:25,252 | `recovery_phase=aws_ready` | Watcher xác nhận AWS sẵn sàng nhận ghi |
| 19:20:56,699 | `shared_writer=aws` | Watcher ghi thành công qua tên miền chung và chuẩn bị rejoin Azure |
| 19:21:23,682 | `recovery_phase=complete` | Azure đã trở lại standby và vượt qua kiểm tra streaming cùng dữ liệu probe |

Từ lúc gửi lệnh dừng tới khi watcher quyết định failover là khoảng **150,3 giây**. Từ quyết định tới khi writer Azure sẵn sàng ở endpoint trực tiếp mất **1,3 giây**. Từ mốc writer ở Azure tới mẫu ghi đầu tiên qua tên miền chung trên laptop là khoảng **91,7 giây**. Khoảng cuối có thể chịu ảnh hưởng của health check, DNS và nhịp lấy mẫu. Journal và CSV ghi từ hai máy khác nhau, nên các chênh lệch giữa hai nguồn được trình bày dưới dạng xấp xỉ.

Watcher bắt đầu `drain_azure` khoảng **304,0 giây** sau khi nó xác nhận ghi thành công qua tên miền chung trên Azure, phù hợp với cửa sổ writer tối thiểu 300 giây của bài demo. Toàn bộ vòng từ yêu cầu dừng EC2 đến khi standby Azure khôi phục mất khoảng **11 phút 23,4 giây**. Mốc này hữu ích khi quyết định lúc có thể bắt đầu lượt thử kế tiếp.

## Bước 4 — Chuẩn bị baseline AWS-only

Baseline dùng lại EC2 và ứng dụng trên AWS. Client truy cập `aws.mcf.todicode.tech` để đo đường phục hồi trên chính EC2. Dùng cùng laptop, workload probe, chu kỳ mục tiêu 2 giây và cửa sổ 20 phút của B01.

AWS CloudTrail ghi `StopInstances` lúc **19:10:09 UTC** và `StartInstances` lúc **19:14:13 UTC** cho EC2 của B01. `StartInstances` là yêu cầu do `mcf-azure-watcher` gửi và AWS trả trạng thái `pending`. Tính từ mốc laptop ghi trước khi gọi lệnh dừng lúc **19:10:00,264 UTC**, khoảng chờ là **252,7 giây**. A01 dùng lịch gửi yêu cầu bật lại ở **T+253 giây**, với T là mốc laptop ghi ngay trước lệnh dừng. Đây là khoảng chờ được chọn để so theo lịch phục hồi của B01.

Tắt riêng VM Azure để watcher và standby dừng. Lệnh `az vm stop` giữ cấp phát của VM.

```bash
azure_vm_id=$(terraform -chdir=deploy/terraform/azure output -raw azure_vm_id)

az vm stop --ids "$azure_vm_id" --only-show-errors

az vm get-instance-view --ids "$azure_vm_id" \
  --query "instanceView.statuses[?starts_with(code, 'PowerState/')].code | [0]" \
  --output tsv

/c/Windows/System32/curl.exe -fsS --max-time 10 \
  https://aws.mcf.todicode.tech/health/database
```

Kết quả chuẩn bị được xác nhận là Azure `PowerState/stopped` và AWS `role=primary`, `writable=true`, `writes_paused=false`. A01 bắt đầu từ trạng thái này.

## Bước 5 — Đo phục hồi AWS-only, lượt A01

Chạy probe trực tiếp qua hostname AWS từ Git Bash trên laptop. Giữ VM Azure ở trạng thái `stopped` trong suốt lượt đo.

```bash
mkdir -p experiments/runs
run_id="stage9-a01-$(date -u +%Y%m%dT%H%M%SZ)"

.venv/Scripts/python.exe -u scripts/probe_failover.py \
  --url https://aws.mcf.todicode.tech \
  --interval 2 \
  --duration 1200 \
  --timeout 3 \
  --fresh-connections \
  --run-id "$run_id" \
  --out "experiments/runs/$run_id.csv"
```

Khi probe đã đọc và ghi qua AWS trong khoảng 90 giây, dùng Git Bash thứ hai để nhận ID và gửi lệnh dừng.

```bash
read -r -p 'Paste the run ID from Terminal 1: ' run_id
```

```bash
aws_instance_id=$(terraform -chdir=deploy/terraform/aws output -raw aws_instance_id)
fault_log="experiments/runs/$run_id.fault.log"

if [[ "$run_id" =~ ^stage9-a01-[0-9]{8}T[0-9]{6}Z$ &&
      "$aws_instance_id" =~ ^i-[0-9a-f]+$ &&
      ! -e "$fault_log" ]]; then
  (
    set -o pipefail
    aws_ec2=(aws --profile default --region ap-southeast-1 --no-cli-pager ec2)
    {
      SECONDS=0
      printf 'stop_requested_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
      "${aws_ec2[@]}" stop-instances --instance-ids "$aws_instance_id" \
        --query 'StoppingInstances[0].CurrentState.Name' --output text || exit 1
      "${aws_ec2[@]}" wait instance-stopped --instance-ids "$aws_instance_id" || exit 1

      remaining=$((253 - SECONDS))
      if (( remaining > 0 )); then
        printf 'Restart scheduled in %s seconds. Keep this terminal open.\n' "$remaining"
        sleep "$remaining"
      fi

      printf 'start_requested_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
      "${aws_ec2[@]}" start-instances --instance-ids "$aws_instance_id" \
        --query 'StartingInstances[0].CurrentState.Name' --output text || exit 1
      "${aws_ec2[@]}" wait instance-running --instance-ids "$aws_instance_id" || exit 1
      printf 'instance_running_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)"
    } 2>&1 | tee "$fault_log"
  )
else
  printf 'Check the run ID, EC2 instance ID, and fault log before retrying.\n' >&2
fi
```

Sau khi CLI thấy EC2 `running`, SSH vào AWS, khởi động WireGuard và cho phép K3s chạy với startup guard hiện có. Ghi mốc gửi lệnh `systemctl start k3s` từ host AWS.

```bash
sudo systemctl start wg-quick@wg0 &&
sudo touch /run/issues-k3s-start-approved &&
sudo systemctl reset-failed k3s &&
date -u '+k3s_start_requested_at_utc=%Y-%m-%dT%H:%M:%S.%3NZ' &&
sudo systemctl start k3s
```

### Kết quả phía client

Lượt dùng để so sánh là `stage9-a01-20261120T202632Z`. Lượt trước đó bị ngắt trong khi chờ bật lại EC2 và được giữ làm dữ liệu thử. Lượt A01 dùng cho báo cáo có **493 mẫu**, gồm **91,3 giây** trước lỗi. Lệnh bật lại được gửi ở **T+253,5 giây**, lệch 0,5 giây so với lịch đã chọn.

| Sự kiện | Giờ UTC ngày 20/11/2026 |
|---|---|
| Gửi yêu cầu dừng EC2 | 20:28:04,037 |
| Gửi yêu cầu bật lại EC2 | 20:32:17,537 |
| CLI quan sát EC2 `running` | 20:32:35,172 |
| Gửi lệnh mở K3s | 20:33:14,484 |
| Mẫu đầu ghi thành công trở lại qua AWS | 20:33:37,386 (`seq=106`) |

Tổng thời gian quan sát từ yêu cầu dừng đến mẫu ghi phục hồi là **333,3 giây**. Sau yêu cầu bật lại EC2, CLI mất khoảng **17,6 giây** để quan sát `running`. Khoảng tiếp theo tới lệnh mở K3s là **39,3 giây**, gồm thao tác SSH và mở startup guard. Từ lệnh mở K3s đến mẫu ghi thành công mất khoảng **22,9 giây**. Các khoảng ghép giữa laptop và host AWS dùng mốc UTC và có sai số do lấy mẫu cùng đồng hồ hai máy.

| Chỉ số | Đọc `GET /version` | Ghi `POST /api/ping` |
|---|---:|---:|
| Thành công | 434/493 | 434/493 |
| Tỷ lệ lỗi | 12,0% | 12,0% |
| p50 / p95 của request thành công | 93 / 125 ms | 107 / 132 ms |
| Gián đoạn | 332,5 s | 332,5 s |

Đối chiếu cuối lượt tìm thấy đủ **434/434** bản ghi được xác nhận.

### So sánh cặp A01 và B01

| Chỉ số | A01 — AWS-only | B01 — AWS + Azure standby |
|---|---:|---:|
| Lệnh dừng đến mẫu ghi phục hồi đầu tiên | 333,3 s | 243,3 s |
| Gián đoạn ghi ban đầu | 332,5 s | 243,1 s |
| Gián đoạn ghi khi failback | N/A | 86,2 s |
| Tổng gián đoạn ghi trong cửa sổ đo | 332,5 s | 329,3 s |
| Bản ghi đã xác nhận tìm thấy cuối lượt | 434/434 | 437/437 |

Trong cặp thử này, mô hình hai cloud cho phép ghi trở lại sớm hơn khoảng **90 giây**. Tổng gián đoạn ghi gần nhau khi tính cả failback. Kết quả áp dụng cho lịch bật lại EC2 đã chọn và quy trình mở K3s của hai cấu hình. Các cặp thử lặp lại sẽ kiểm tra độ ổn định của chênh lệch.

## Bước 6 — Khôi phục hệ hai cloud để chuẩn bị B02

Bật cả hai VM. Vì lượt A01 kết thúc với AWS primary, mở K3s trên AWS trước. Sau khi AWS nhận ghi, mở K3s trên Azure bằng cùng lệnh trong phiên SSH trên từng máy.

```bash
sudo systemctl start wg-quick@wg0 &&
sudo touch /run/issues-k3s-start-approved &&
sudo systemctl reset-failed k3s &&
sudo systemctl start k3s
```

Trên Azure, kiểm tra `sudo systemctl is-active mcf-watcher`. Từ laptop, đối chiếu vai trò từng origin và đích mà tên miền chung đang phục vụ.

```bash
/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\n' \
  https://aws.mcf.todicode.tech/health/database

/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\n' \
  https://azure.mcf.todicode.tech/api/database/status

/c/Windows/System32/curl.exe -fsS --max-time 10 -w '\n' \
  https://app.mcf.todicode.tech/version
```

Cả hai origin và tên miền chung trả HTTP 200 cho các endpoint trên. AWS là `primary`, `writable=true`. Azure là `standby`, `replication_connected=true`, với LSN nhận và phát lại cùng bằng `0/170763C0` tại thời điểm kiểm tra. Tên miền chung trả `environment=aws`. Watcher báo `active`, `auto_failover=True auto_recovery=True` và vòng trước ở `phase=complete`.

## Bước 7 — Chuẩn bị bộ ghi mốc DNS cho B02

[Bộ quan sát DNS](../../experiments/observe_dns.ps1) lưu các dòng CSV dạng `utc,source,result`. `route53_authoritative` là CNAME do `ns-1064.awsdns-05.org` trả về. `windows_dns_cache` là IPv4 đã có trong cache Windows tại thời điểm đọc. Script truy vấn nameserver qua `nslookup` và dùng `Resolve-DnsName -CacheOnly` cho phép đo ở laptop. Nó ghi thời điểm UTC riêng sau khi nhận từng kết quả.

Để chạy thử khi AWS đang nhận ghi, phân giải tên miền một lần rồi lấy dữ liệu trong sáu giây từ Git Bash.

```bash
.venv/Scripts/python.exe -c "import socket; socket.getaddrinfo('app.mcf.todicode.tech', 443, socket.AF_INET, socket.SOCK_STREAM)"

powershell.exe -NoProfile -File experiments/observe_dns.ps1 -DurationSeconds 6
```

Cả ba cặp mẫu lúc 10:12:56–10:13:01 UTC ngày 21/11/2026 cho CNAME `aws.mcf.todicode.tech` từ Route 53 và IPv4 `175.41.152.242` trong cache Windows. Khi chạy B02, probe HTTP sẽ phân giải tên miền theo quy trình bình thường. So sánh các mốc DNS với lần ghi thành công đầu tiên để phân biệt khi nameserver đã đổi đích, khi laptop thấy IP mới và khi ứng dụng xác nhận ghi thành công.

## Bước 8 — Đo failover trên hai cloud, lượt B02

Tạo một ID dùng chung cho log DNS, CSV HTTP và fault log. Mở ba terminal Git Bash tại thư mục gốc repo, tạo ID ở terminal thứ nhất và nhập cùng giá trị ở hai terminal còn lại.

```bash
mkdir -p experiments/runs
run_id="stage9-b02-$(date -u +%Y%m%dT%H%M%SZ)"
printf 'Run ID: %s\n' "$run_id"
```

Terminal 2 chạy bộ quan sát DNS trong 21 phút để phủ cửa sổ của probe HTTP.

```bash
read -r -p 'Paste the run ID from Terminal 1: ' run_id

powershell.exe -NoProfile -File experiments/observe_dns.ps1 -DurationSeconds 1260 |
  tee "experiments/runs/$run_id.dns.csv"
```

Khi nameserver trả CNAME AWS, quay lại Terminal 1 để chạy probe HTTP 20 phút với kết nối mới trên từng request.

```bash
.venv/Scripts/python.exe -u scripts/probe_failover.py \
  --url https://app.mcf.todicode.tech \
  --interval 2 \
  --duration 1200 \
  --timeout 3 \
  --fresh-connections \
  --run-id "$run_id" \
  --out "experiments/runs/$run_id.csv"
```

Sau khoảng 90 giây ghi thành công qua AWS, dùng Terminal 3 để gửi một lệnh dừng EC2 theo cách ở B01. Trong khối lệnh ở Bước 3, dùng tiền tố `stage9-b02-` cho kiểm tra `run_id`. Trước khi gửi lệnh, đối chiếu file `experiments/runs/$run_id.dns.csv` phải có cả `route53_authoritative,aws.mcf.todicode.tech` và `windows_dns_cache,175.41.152.242`. Lưu lệnh dừng và mốc UTC vào `.fault.log`. Giữ watcher chạy và chờ `recovery_phase=complete` của operation mới.

### Kết quả B02

Lượt `stage9-b02-20261121T101841Z` ghi 523 mẫu HTTP và 1.210 dòng quan sát DNS. Probe đã chạy **97,6 giây** trước khi gửi lệnh dừng. Có 274 mẫu ghi thành công qua AWS và 154 qua Azure. Đối chiếu cuối lượt tìm thấy đủ **428/428** bản ghi đã xác nhận. Watcher ghi `recovery_phase=complete` lúc **10:32:55,962 UTC** cho operation `e4f70d5edbdc49418bdcfe30789c8daf`.

| Chỉ số | Đọc `GET /version` | Ghi `POST /api/ping` |
|---|---:|---:|
| Thành công | 434/523 | 428/523 |
| Tỷ lệ lỗi | 17,0% | 18,2% |
| p50 / p95 của request thành công | 101 / 140 ms | 114 / 134 ms |
| Gián đoạn failover | 234,1 s | 230,9 s |
| Gián đoạn failback | 102,1 s | 116,2 s |
| Tổng gián đoạn | 336,2 s | 347,1 s |

| Mốc failover | Giờ UTC ngày 21/11/2026 | Nguồn |
|---|---|---|
| Gửi yêu cầu dừng EC2 | 10:21:43,103 | Fault log |
| Quyết định failover | 10:24:13,565 | `failover_pending` trong journal |
| Endpoint trực tiếp Azure xác nhận writer | 10:24:14,722 | `writer_confirmed` trong journal |
| Nameserver được quan sát trả CNAME Azure | 10:25:25,931 | `route53_authoritative` |
| Mẫu đầu chứa POST thành công qua Azure bắt đầu | 10:25:34,758 | CSV HTTP, `seq=88` |
| Phản hồi POST thành công, ước tính | 10:25:37,923 | `at + read_ms + write_ms` của `seq=88` |
| Lần đầu bộ ghi thấy IP Azure trong cache Windows | 10:25:38,383 | `windows_dns_cache` |

Từ lệnh dừng đến mẫu đầu chứa lượt ghi thành công là **231,7 giây**, theo cùng quy ước đầu mẫu với B01. Mẫu đầu tiên có GET mất khoảng 3 giây rồi mới gửi POST, nên thời điểm nhận phản hồi ghi thành công ước tính ở **T+234,8 giây**. Bộ ghi DNS đọc cache theo nhịp riêng, lần đầu quan sát IP Azure xảy ra khoảng 0,5 giây sau mốc phản hồi ước tính.

Từ endpoint Azure xác nhận writer đến khi nameserver được quan sát trả CNAME Azure mất khoảng **71,2 giây**. Từ mốc DNS đó đến phản hồi POST thành công mất khoảng **12,0 giây**. Điều này thu hẹp phần cần đo tiếp về phía health check và thời điểm nameserver thấy đích mới. Phép đo dùng một nameserver, một laptop và mốc UTC lấy mẫu riêng giữa các nguồn.

CloudTrail ghi watcher gọi `StartInstances` lúc **10:25:46 UTC**, khoảng **242,9 giây** sau mốc gửi lệnh dừng từ laptop. Chọn **T+243 giây** cho lịch gửi yêu cầu bật lại của A02, với khoảng **98 giây** probe trước lỗi. Dữ liệu thô của B02 gồm CSV HTTP, CSV DNS, fault log, summary JSON và journal watcher trong `experiments/runs/`.

## Bước 9 — Chuẩn bị baseline AWS-only cho A02

Tắt riêng Azure để standby và watcher dừng như trong A01. Dùng origin AWS cho phép đo và giữ thời lượng, chu kỳ mục tiêu, workload cùng chế độ kết nối như B02. Khoảng chờ gửi lệnh bật EC2 là **243 giây** kể từ mốc gửi lệnh dừng. Cửa sổ trước lỗi dự kiến khoảng **98 giây**.

```bash
azure_vm_id=$(terraform -chdir=deploy/terraform/azure output -raw azure_vm_id)

az vm stop --ids "$azure_vm_id" --only-show-errors &&
az vm get-instance-view --ids "$azure_vm_id" \
  --query "instanceView.statuses[?starts_with(code, 'PowerState/')].code | [0]" \
  --output tsv

/c/Windows/System32/curl.exe -fsS --max-time 10 \
  https://aws.mcf.todicode.tech/health/database
```

Lần kiểm tra trước khi đo ghi nhận Azure `PowerState/stopped`. AWS trả `role=primary`, `writable=true`, `writes_paused=false` và `current_lsn=0/1B01E0F0`.

## Bước 10 — Đo phục hồi AWS-only, lượt A02

Trong Git Bash tại thư mục repo, chạy probe tới origin AWS với cùng thời lượng và nhịp mục tiêu như B02.

```bash
mkdir -p experiments/runs
run_id="stage9-a02-$(date -u +%Y%m%dT%H%M%SZ)"

.venv/Scripts/python.exe -u scripts/probe_failover.py \
  --url https://aws.mcf.todicode.tech \
  --interval 2 \
  --duration 1200 \
  --timeout 3 \
  --fresh-connections \
  --run-id "$run_id" \
  --out "experiments/runs/$run_id.csv"
```

Đến khoảng `seq=49`, xác nhận đọc và ghi đang thành công. Trong Terminal 2, nhập cùng `run_id` và dùng khối lệnh dừng rồi bật lại EC2 ở Bước 5 với hai giá trị dành cho A02.

```bash
# Run ID guard for A02
[[ "$run_id" =~ ^stage9-a02-[0-9]{8}T[0-9]{6}Z$ ]]

# Remaining time after confirming the instance stopped
remaining=$((243 - SECONDS))
```

Giữ nguyên các bước đợi EC2 dừng và đợi EC2 khởi động trong khối điều khiển. Khi có `instance_running_at_utc`, mở K3s qua startup guard theo Bước 5 và ghi lại `k3s_start_requested_at_utc`.

### Kết quả A02

Lượt `stage9-a02-20261121T110016Z` ghi **501 mẫu** và có **112,7 giây** đo trước lỗi, dài hơn **15,1 giây** so với B02. Lệnh bật lại được gửi ở **T+243,088 giây**, lệch khoảng **0,09 giây** so với lịch đã chọn.

| Mốc phục hồi | Giờ UTC ngày 21/11/2026 | Thời gian từ mốc liền trước |
|---|---|---:|
| Gửi lệnh dừng EC2 | 11:02:09,377 | — |
| Gửi lệnh bật lại EC2 | 11:06:12,465 | 243,1 s |
| CLI quan sát EC2 `running` | 11:06:30,020 | 17,6 s |
| Gửi lệnh mở K3s từ phiên SSH | 11:06:50,895 | 20,9 s |
| Mẫu đầu chứa lượt ghi thành công qua AWS | 11:07:15,109 (`seq=111`) | 24,2 s |

Từ lệnh dừng đến mẫu phục hồi đầu tiên là **305,7 giây**. Mẫu này có GET hết thời gian chờ, rồi POST mới ghi thành công. Từ hai thời lượng riêng trong CSV, thời điểm nhận phản hồi POST ước tính là **11:07:18,285 UTC**, tương ứng **T+308,9 giây**. Dùng quy ước đầu mẫu cho bảng so sánh để giữ cùng cách tính với các lượt trước.

| Chỉ số | Đọc `GET /version` | Ghi `POST /api/ping` |
|---|---:|---:|
| Thành công | 447/501 | 448/501 |
| Tỷ lệ lỗi | 10,8% | 10,6% |
| p50 / p95 của request thành công | 108 / 335 ms | 123 / 353 ms |
| Gián đoạn | 307,2 s | 304,0 s |

Đối chiếu cuối lượt tìm thấy đủ **448/448** bản ghi đã xác nhận. Khi diễn giải tỷ lệ lỗi toàn cửa sổ, ghi rõ độ dài khác nhau của phần trước lỗi. Tệp CSV, fault log và summary JSON được giữ trong `experiments/runs/`.

## Bước 11 — Đưa Azure về standby trước B03

Sau A02, AWS tiếp tục nhận ghi. Bật lại VM Azure, rồi kết nối SSH và cho phép K3s chạy trên Azure.

```bash
ssh -i ~/.ssh/mcf-lab azureuser@4.145.30.250
```

```bash
sudo systemctl start wg-quick@wg0 &&
sudo touch /run/issues-k3s-start-approved &&
sudo systemctl reset-failed k3s &&
sudo systemctl start k3s

sudo systemctl is-active mcf-watcher
grep -m 1 '"phase"' "$HOME/.local/state/mcf-controller/state.json"
```

Kiểm tra vai trò database và tên miền chung theo Bước 6. Trước B03, AWS được xác nhận là writer, Azure là standby đang streaming với LSN nhận và phát lại bằng `0/1B056F78`, tên miền chung trả `environment=aws`. Watcher báo `active`, bật cả failover và recovery tự động, và vòng phục hồi trước ở `phase=complete`.

## Bước 12 — Đo failover trên hai cloud, lượt B03

Lặp cấu hình và quy trình ba terminal ở Bước 8. Tạo ID với tiền tố B03 ở Terminal 1 rồi nhập cùng ID vào Terminal 2 và Terminal 3 trước khi chạy probe HTTP.

```bash
mkdir -p experiments/runs
run_id="stage9-b03-$(date -u +%Y%m%dT%H%M%SZ)"
printf 'Run ID: %s\n' "$run_id"
```

Chuẩn bị các biến ở Terminal 3 để gửi lệnh dừng gần mốc đã chọn.

```bash
aws_instance_id=$(terraform -chdir=deploy/terraform/aws output -raw aws_instance_id)
dns_log="experiments/runs/$run_id.dns.csv"
fault_log="experiments/runs/$run_id.fault.log"
```

Chạy bộ ghi DNS 21 phút ở Terminal 2 và probe HTTP 20 phút ở Terminal 1 theo lệnh B02. Khi probe gần `seq=44` và vẫn đọc, ghi thành công qua AWS, gửi một lệnh dừng EC2 bằng khối lệnh Bước 3. Dùng tiền tố `stage9-b03-` trong kiểm tra `run_id`, đối chiếu hai mẫu DNS AWS như bước B02 rồi lưu mốc vào `.fault.log`. Watcher tiếp tục cả vòng cho tới `recovery_phase=complete`.

### Kết quả B03

Lượt `stage9-b03-20261121T113203Z` có **520 mẫu HTTP**, **1.212 dòng quan sát DNS** và **90,1 giây** probe trước lỗi. Có 285 mẫu ghi thành công qua AWS và 150 qua Azure. Đối chiếu cuối lượt tìm thấy đủ **435/435** bản ghi đã xác nhận. Watcher báo `recovery_phase=complete` lúc **11:46:11,713 UTC** cho operation `d09a5594726841909b6e7762b721dda9`.

| Chỉ số | Đọc `GET /version` | Ghi `POST /api/ping` |
|---|---:|---:|
| Thành công | 441/520 | 435/520 |
| Tỷ lệ lỗi | 15,2% | 16,3% |
| p50 / p95 của request thành công | 104 / 133 ms | 116 / 138 ms |
| Gián đoạn failover | 240,6 s | 240,6 s |
| Gián đoạn failback | 80,1 s | 92,1 s |
| Tổng gián đoạn | 320,7 s | 332,7 s |

| Mốc failover | Giờ UTC ngày 21/11/2026 | Nguồn |
|---|---|---|
| Gửi lệnh dừng EC2 | 11:34:57,448 | Fault log |
| Watcher quyết định failover | 11:37:27,644 | `failover_pending` trong journal |
| Endpoint trực tiếp Azure xác nhận writer | 11:37:28,819 | `writer_confirmed` trong journal |
| Nameserver được quan sát trả CNAME Azure | 11:38:41,132 | `route53_authoritative` |
| Mẫu đầu chứa POST thành công qua Azure bắt đầu | 11:38:58,267 (`seq=86`) | CSV HTTP |
| Phản hồi POST thành công, ước tính | 11:38:58,531 | `at + read_ms + write_ms` của `seq=86` |
| Lần đầu bộ ghi thấy IP Azure trong cache Windows | 11:38:59,819 | `windows_dns_cache` |

Từ lệnh dừng đến mẫu ghi phục hồi đầu tiên là **240,8 giây**. Khoảng từ Azure writer trực tiếp đến CNAME Azure được quan sát là **72,3 giây**, gần với **71,2 giây** của B02. Khoảng tiếp theo tới phản hồi POST trên laptop là khoảng **17,4 giây**. Các con số mô tả thời điểm quan sát trên một nameserver và một laptop, với nhịp lấy mẫu riêng.

CloudTrail ghi `StopInstances` lúc **11:35:07 UTC** và `StartInstances` do watcher gửi lúc **11:39:00 UTC**. Mốc `StartInstances` cách khoảng **242,6 giây** so với thời điểm laptop ghi mốc gửi lệnh dừng. Chọn lịch **T+243 giây** và khoảng **90 giây trước lỗi** cho A03. Dữ liệu CSV HTTP, CSV DNS, fault log, summary JSON và journal watcher của B03 được lưu trong `experiments/runs/`.

## Bước 13 — Chuẩn bị baseline AWS-only cho A03

Tắt riêng VM Azure và kiểm tra writer qua origin AWS theo Bước 9. A03 dùng cùng thời lượng, workload và chế độ kết nối với B03. Giữ khoảng **90 giây** đo trước lỗi và dùng lịch gửi lệnh bật lại EC2 ở **T+243 giây** kể từ mốc gửi lệnh dừng.

Kiểm tra ghi nhận Azure `PowerState/stopped`. Origin AWS trả `role=primary`, `writable=true`, `writes_paused=false` và `current_lsn=0/1F017BF0`. Đây là trạng thái đầu của A03.

## Bước 14 — Đo phục hồi AWS-only, lượt A03

Chuẩn bị Terminal 2 trước khi bắt đầu probe để gửi lệnh dừng gần mốc 90 giây của B03. Trong Terminal 1, tạo ID mới.

```bash
mkdir -p experiments/runs
run_id="stage9-a03-$(date -u +%Y%m%dT%H%M%SZ)"
printf 'Run ID: %s\n' "$run_id"
```

Trong Terminal 2, nhập ID đó và chuẩn bị EC2 ID cùng đường dẫn fault log.

```bash
read -r -p 'Paste the run ID from Terminal 1: ' run_id
```

```bash
aws_instance_id=$(terraform -chdir=deploy/terraform/aws output -raw aws_instance_id)
fault_log="experiments/runs/$run_id.fault.log"
```

Chạy probe ở Terminal 1 với `--url https://aws.mcf.todicode.tech --interval 2 --duration 1200 --timeout 3 --fresh-connections` như Bước 10. Đến khoảng `seq=44` với `read=200 write=200 by=aws`, dùng khối dừng rồi bật EC2 ở Bước 5. Kiểm tra tiền tố `stage9-a03-` khi xác minh ID, dùng `remaining=$((243 - SECONDS))` để khớp lịch B03. Sau `instance_running_at_utc`, mở K3s qua SSH và ghi `k3s_start_requested_at_utc` như A01 và A02. Giữ Azure `stopped` và để probe chạy hết 20 phút.

### Kết quả A03

Lượt `stage9-a03-20261121T115954Z` ghi **505 mẫu**. A03 có **90,3 giây** đo trước lỗi, gần với **90,1 giây** của B03. Lệnh bật lại ở **T+242,603 giây**, khoảng 0,4 giây sớm hơn lịch T+243 và xấp xỉ mốc T+242,6 của watcher trong B03.

| Mốc phục hồi | Giờ UTC ngày 21/11/2026 | Thời gian từ mốc liền trước |
|---|---|---:|
| Gửi lệnh dừng EC2 | 12:02:03,974 | — |
| Gửi lệnh bật lại EC2 | 12:06:06,577 | 242,6 s |
| CLI quan sát EC2 `running` | 12:06:24,169 | 17,6 s |
| Gửi lệnh mở K3s từ phiên SSH | 12:06:41,358 | 17,2 s |
| Mẫu đầu chứa lượt ghi thành công qua AWS | 12:06:59,125 (`seq=98`) | 17,8 s |

Từ lệnh dừng tới mẫu phục hồi đầu tiên là **295,2 giây**. Từ thời lượng GET và POST của mẫu đó, thời điểm nhận phản hồi ghi thành công được ước tính là **12:06:59,366 UTC**. Bảng so sánh dùng mốc đầu mẫu như các lượt trước.

| Chỉ số | Đọc `GET /version` | Ghi `POST /api/ping` |
|---|---:|---:|
| Thành công | 453/505 | 453/505 |
| Tỷ lệ lỗi | 10,3% | 10,3% |
| p50 / p95 của request thành công | 100 / 126 ms | 117 / 142 ms |
| Gián đoạn | 295,3 s | 295,3 s |

Đối chiếu cuối lượt tìm thấy đủ **453/453** bản ghi đã xác nhận. CSV, fault log và summary JSON của A03 nằm trong `experiments/runs/`.

## Tổng hợp A01–A03 và B01–B03

| Lượt | Lệnh dừng đến mẫu ghi phục hồi đầu tiên | Gián đoạn ghi ban đầu | Gián đoạn ghi khi failback | Tổng gián đoạn ghi | Bản ghi đã xác nhận còn lại |
|---|---:|---:|---:|---:|---:|
| A01 AWS-only | 333,3 s | 332,5 s | N/A | 332,5 s | 434/434 |
| B01 AWS + Azure standby | 243,3 s | 243,1 s | 86,2 s | 329,3 s | 437/437 |
| A02 AWS-only | 305,7 s | 304,0 s | N/A | 304,0 s | 448/448 |
| B02 AWS + Azure standby | 231,7 s | 230,9 s | 116,2 s | 347,1 s | 428/428 |
| A03 AWS-only | 295,2 s | 295,3 s | N/A | 295,3 s | 453/453 |
| B03 AWS + Azure standby | 240,8 s | 240,6 s | 92,1 s | 332,7 s | 435/435 |

Tính từ mốc gốc trước khi làm tròn, mô hình hai cloud phục hồi lượt ghi đầu sớm hơn lần lượt **90,0**, **74,1** và **54,3 giây**, với trung bình mô tả **72,8 giây**. Khi tính cả failback, tổng gián đoạn ghi của mô hình hai cloud thấp hơn **3,2 giây** ở cặp 01 và cao hơn **43,1 giây** ở cặp 02 cùng **37,4 giây** ở cặp 03. Cả sáu lượt đều tìm thấy đủ các bản ghi đã được xác nhận, tổng cộng **2.635/2.635**.

Các kết quả mô tả ba cặp đo với cùng workload, cửa sổ 20 phút, lịch gửi lệnh bật EC2 đối chiếu theo từng cặp và thao tác mở K3s thủ công trong AWS-only. Phần phân tích chi phí dùng cùng phạm vi tài nguyên và thời lượng cho hai cấu hình theo tiêu chí đánh giá của dự án.

## Bước 15 — Tính cost proxy

So sánh hai kiến trúc theo một tháng quy ước **730 giờ**, giả định compute của mỗi kiến trúc chạy liên tục và disk cùng IP được giữ cả tháng. Giá niêm yết bằng USD được tra ngày **21/11/2026**, trước thuế, credit và ưu đãi tài khoản. AWS-only gồm hạ tầng AWS cần để phục vụ workload. Việc giữ tài nguyên Azure khi chạy baseline trong lab được tính riêng nếu đối chiếu hóa đơn.

| Hạng mục | Đơn giá USD | Cấu hình áp dụng |
|---|---:|---|
| EC2 `t3.medium` Linux On-Demand, Singapore | 0,0528/giờ | Cả hai |
| EBS `gp3` 30 GiB, Singapore | 0,096/GB-tháng | Cả hai |
| Một Elastic IPv4 AWS | 0,005/giờ | Cả hai |
| Một Standard Public Hosted Zone Route 53 | 0,50/tháng | Cả hai |
| Azure `Standard_B2ls_v2` Linux, Southeast Asia | 0,0528/giờ | Multi-cloud |
| Azure Standard SSD `E4 LRS` 32 GiB | 2,40/tháng | Multi-cloud |
| Một Azure Standard Static IPv4 | 0,005/giờ | Multi-cloud |
| Route 53 standard HTTPS health check tới AWS | 0,50 + 1,00/tháng | Multi-cloud |
| Route 53 standard HTTPS health check tới Azure | 0,75 + 2,00/tháng | Multi-cloud |

Giá EC2 và EBS lấy từ AWS Price List Query API với service `AmazonEC2`, region tài nguyên `ap-southeast-1`, SKU `USWP83ASNCY4BSQF` và `X8SY8CJFS8WV7VQN`. Giá Azure lấy từ Retail Prices API cho `southeastasia`, với các meter `B2ls v2` của sản phẩm Linux `Virtual Machines Bsv2 Series`, `E4 LRS Disk` và `Standard IPv4 Static Public IP`. Hai health check sử dụng HTTPS, chu kỳ 30 giây và tắt đo latency. [AWS Price List Query API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-price-list-query-api.html) · [Giá AWS public IPv4](https://aws.amazon.com/vpc/pricing/) · [Giá Route 53](https://aws.amazon.com/route53/pricing/) · [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)

Chạy công thức bằng `Decimal` để giữ số gốc và làm tròn khi hiển thị.

```bash
.venv/Scripts/python.exe - <<'PY'
from decimal import Decimal as D

hours = D("730")
aws_compute = hours * D("0.0528")
aws_disk = D("30") * D("0.096")
aws_ip = hours * D("0.005")
dns_zone = D("0.50")

azure_compute = hours * D("0.0528")
azure_disk = D("2.40")
azure_ip = hours * D("0.005")
https_checks = D("0.50") + D("1.00") + D("0.75") + D("2.00")

aws_only = aws_compute + aws_disk + aws_ip + dns_zone
multi_cloud = aws_only + azure_compute + azure_disk + azure_ip + https_checks

def usage_cost(dns_queries, paid_egress_gb, azure_disk_ops=0):
    return (
        D(dns_queries) * D("0.40") / D("1000000")
        + D(paid_egress_gb) * D("0.12")
        + D(azure_disk_ops) * D("0.002") / D("10000")
    )

example_usage = usage_cost(100_000, 0)

print(f"AWS-only fixed cost: ${aws_only:.2f}")
print(f"Multi-cloud fixed cost: ${multi_cloud:.2f}")
print(f"Additional fixed cost: ${multi_cloud - aws_only:.2f}")
print(f"Multi-cloud / AWS-only: {multi_cloud / aws_only:.2f}x")
print(f"AWS-only with example usage: ${aws_only + example_usage:.2f}")
print(f"Multi-cloud with example usage: ${multi_cloud + example_usage:.2f}")
PY
```

Các khoản theo lượng dùng gồm DNS query, dữ liệu gửi ra Internet chịu phí như lưu lượng WireGuard liên cloud, và giao dịch Standard SSD Azure chịu phí. Ví dụ đặt **100.000 truy vấn DNS** cho mỗi cấu hình và nhập **0** cho egress chịu phí cùng số giao dịch đĩa chịu phí để minh họa. Đơn giá egress `0,12 USD/GB` dùng cho bậc thu phí đầu tiên ở Singapore và Azure Southeast Asia qua Microsoft Global Network. Phần tính cố định và ví dụ theo lượng dùng được báo riêng. [Amazon EC2 Data Transfer](https://aws.amazon.com/ec2/pricing/on-demand/#Data_Transfer) · [Azure Bandwidth](https://azure.microsoft.com/en-us/pricing/details/bandwidth/) · [Azure Managed Disks](https://azure.microsoft.com/en-us/pricing/details/managed-disks/)

| Kết quả được xác nhận | AWS-only | AWS + Azure standby |
|---|---:|---:|
| Chi phí cố định theo tháng quy ước | 45,57 USD | 94,42 USD |
| Chi phí với lượng dùng minh họa | 45,61 USD | 94,46 USD |

Chi phí cố định tăng **48,84 USD/tháng** trên số gốc, với tỷ lệ **2,07 lần**. Trong ba cặp thử, warm standby rút ngắn thời gian đến mẫu ghi phục hồi đầu tiên trung bình **72,8 giây**. Tổng gián đoạn ghi dài hơn ở hai cặp sau khi tính failback. Hai chỉ số thời gian và cost proxy cần được trình bày cùng phạm vi thí nghiệm khi diễn giải đánh đổi.

## Bước 16 — Vẽ và đọc biểu đồ phục hồi ghi

Script đọc `*.fault.log`, `*.csv` và `*.summary.json` của sáu lượt A01–A03 và B01–B03 đã chọn trong `experiments/runs/`. Fault log cung cấp mốc gửi lệnh dừng EC2, CSV cung cấp mẫu ghi HTTP 200 đầu tiên tại site phục hồi, còn JSON cung cấp các khoảng gián đoạn ghi. [Script tạo biểu đồ](../../experiments/plot_write_recovery.py)

Chạy từ thư mục gốc của repo trong Git Bash. Môi trường Python riêng cho biểu đồ giữ bộ thư viện chạy probe và watcher độc lập với Matplotlib.

```bash
.venv/Scripts/python.exe -m venv experiments/runs/.plot-venv
experiments/runs/.plot-venv/Scripts/python.exe -m pip install "matplotlib==3.11.2"
experiments/runs/.plot-venv/Scripts/python.exe experiments/plot_write_recovery.py
```

Script lưu ảnh vào `experiments/runs/write_recovery_comparison.png`.

- **Time to first successful write** đo từ lúc gửi lệnh dừng EC2 tới mẫu ghi thành công đầu tiên ở site phục hồi. Kiến trúc dùng Azure standby phục hồi ghi sớm hơn trong cả ba cặp, trung bình **72,8 giây**.
- **Total write downtime** cộng các khoảng gián đoạn ghi quan sát được. Phần xanh lục là gián đoạn ban đầu, phần cam là gián đoạn khi failback về AWS. Số trên đỉnh cột chồng là tổng của hai phần, lần lượt **329,3**, **347,1** và **332,7 giây**. Tổng ở cấu hình hai cloud cao hơn AWS-only trong hai trên ba cặp.

Hai biểu đồ dùng mốc bắt đầu khác nhau. Thời gian phục hồi lấy mốc từ fault log, còn khoảng gián đoạn bắt đầu tại mẫu ghi lỗi đầu tiên được probe quan sát. Chênh lệch nhỏ giữa hai số của cùng một lượt là phù hợp với cách lấy mẫu.
