# Phạm vi và tiêu chí nghiệm thu

Project: **29 - Multi-Cloud Deployment & Failover**, học phần Distributed Computing Systems.

Tài liệu này là checklist tham chiếu xuyên suốt quá trình triển khai. Phân biệt các nội dung Suggested tasks / requirements của đề tài 29, General Deliverables của học phần, rubric đánh giá và quyết định kỹ thuật của project. Chỉ ghi hoàn thành khi có bằng chứng thực hành tương ứng.

Phần đối chiếu trong đề bài: mô tả đề tài 29 và Assessment Rubric ở trang 14; General Deliverables ở trang 14-15. Phần tổng quan trang 2 nhấn mạnh implementation, thí nghiệm lặp lại được, số đo, phân tích và report/demo; quy mô nhóm 3-4 sinh viên được ghi là khuyến nghị.

## 1. Suggested tasks / requirements của đề tài 29

Project đặt mục tiêu đáp ứng đầy đủ năm nội dung suggested sau:

| ID | Nội dung đề tài | Cách thực hiện trong project | Bằng chứng cần có |
|---|---|---|---|
| S1 | Cùng một ứng dụng trên hai môi trường hoặc cluster độc lập | AWS primary và Azure warm standby; hai K3s độc lập; cùng application image digest | Inventory hai môi trường, trạng thái workload, định danh image và kiểm tra ứng dụng tại từng origin |
| S2 | Health monitoring và chuyển traffic/failover | Theo dõi liveness, database role và writer health; chuyển traffic bằng DNS sau khi writer đích sẵn sàng | Kết quả health check, timeline chuyển writer/traffic, request tới môi trường phục vụ mới |
| S3 | Mô phỏng lỗi hoàn toàn một môi trường | Bài thử làm mất khả dụng toàn bộ môi trường primary theo kịch bản kiểm soát | Mốc fault injection, bằng chứng origin primary không phục vụ, standby tiếp quản và kiểm tra dữ liệu |
| S4 | Đo failover time, downtime, latency và simple cost proxy | Probe từ ngoài hai môi trường; lưu kết quả thô và tính chỉ số theo mốc thời gian đã định nghĩa | Script, workload, CSV/JSON, bảng/biểu đồ, công thức và giả định cost proxy |
| S5 | Ghi lại độ phức tạp vận hành và các trade-off multi-cloud | Phân tích mạng liên cloud, DNS, replication bất đồng bộ, fencing, promote, recovery và chi phí | Runbook, tình huống giới hạn, kết quả thực nghiệm và thảo luận các đánh đổi |

S3 cần một tình huống mất khả dụng cả môi trường; một bài thử chỉ restart pod hoặc process chưa đủ để chứng minh tình huống này.

Đề tài liệt kê Kubernetes, Prometheus và giải pháp DNS/load balancer trong phần Tools; Terraform được ghi rõ là optional. Việc dùng Terraform, K3s, Route 53, Traefik, WireGuard và PostgreSQL là lựa chọn triển khai của project. Đề không chỉ định phải dùng AWS ALB, RDS hay một dịch vụ managed cụ thể.

## 2. General Deliverables

Các đầu ra chung phải được đối chiếu cùng với nội dung đề tài:

| ID | Đầu ra | Điều kiện nghiệm thu của project |
|---|---|---|
| G1 | Source code và deployment/run instructions | Code có cấu hình mẫu phù hợp; hướng dẫn triển khai, cấu hình, chạy và kiểm tra được trên account của người tái dựng |
| G2 | Sơ đồ kiến trúc và giải thích các thành phần phân tán | Sơ đồ khớp hệ đã triển khai; giải thích request flow, DNS, replication, health check và failover control |
| G3 | Ít nhất một baseline hoặc phương án thay thế để so sánh | Có cấu hình so sánh thực sự và kết quả đo; chỉ mô tả một phương án trên giấy chưa phải bằng chứng so sánh |
| G4 | Script thí nghiệm lặp lại được và mô tả workload | Ghi điều kiện chạy, tải, thời gian, cách tạo lỗi, số lần lặp và cách reset; lưu dữ liệu thô theo từng run |
| G5 | Metrics, bảng/biểu đồ và diễn giải kết quả | Có số đo, đơn vị, cách tính, phân tích kết quả và giới hạn; dashboard/screenshot đơn lẻ không thay thế phân tích |
| G6 | Tình huống failure hoặc stress khi phù hợp | Với đề tài 29, có bài thử mất khả dụng môi trường và quan sát quá trình phục hồi |
| G7 | Final technical report và live/demo video hoặc presentation | Báo cáo mô tả thiết kế, phương pháp, triển khai, baseline, kết quả và trade-off; chuẩn bị phần trình diễn theo hình thức học phần yêu cầu |

PDF không nêu số trang cụ thể cho báo cáo. Giới hạn số trang hoặc yêu cầu trình diễn cụ thể trong hướng dẫn học phần bổ sung cần được đối chiếu riêng, không gán nhầm thành quy định của PDF này.

## 3. Assessment Rubric

| Tiêu chí | Trọng số | Nội dung cần chứng minh |
|---|---:|---|
| System design & distributed-systems concepts | 20% | Thiết kế hai môi trường độc lập; luồng dữ liệu/điều khiển; các khái niệm availability, replication, consistency và failure domains |
| Implementation quality & reproducibility | 25% | Hệ chạy được, code/cấu hình rõ ràng, hướng dẫn tái dựng và bằng chứng kiểm tra |
| Experimental design & metrics | 20% | Workload, kịch bản lỗi, phương pháp đo, các lần chạy lặp và số liệu thô |
| Analysis, discussion & comparison with baseline | 20% | So sánh có số liệu, giải thích khác biệt, trade-off và giới hạn |
| Demo, report & presentation | 15% | Trình diễn hoạt động và báo cáo/thuyết trình rõ ràng, khớp kết quả thực tế |

Hai phần thí nghiệm/số đo và phân tích/so sánh chiếm tổng cộng 40%. Triển khai thành công là một mốc quan trọng, chưa thay thế được hai phần này.

## 4. Baseline và nguyên tắc đo

Baseline được chọn là cùng ứng dụng trên một môi trường AWS, so sánh với mô hình AWS primary + Azure standby. Tái sử dụng phần AWS của project cho baseline; không cần một ứng dụng hay repository triển khai riêng. Chốt cấu hình và quy trình reset khi bắt đầu giai đoạn thí nghiệm; giữ workload, client đo và cửa sổ quan sát tương đương.

Baseline một môi trường không có đích failover. Khi chỉ số không áp dụng, ghi rõ N/A và so sánh downtime/recovery time phù hợp; không tự gán failover time bằng không. Một phương án thay thế khác có thể dùng nếu được thiết kế và đo rõ ràng, vì General Deliverables cho phép baseline hoặc alternative approach.

### 4.1. Hai cấu hình so sánh được đề xuất

| Thành phần | A: AWS-only baseline | B: AWS primary + Azure warm standby |
|---|---|---|
| Ứng dụng | Cùng image digest trên AWS | Cùng image digest trên AWS và Azure |
| Primary | PostgreSQL trên AWS | PostgreSQL trên AWS |
| Standby | Không có standby hoạt động | PostgreSQL Azure nhận WAL bất đồng bộ |
| Đường truy cập | Hostname HTTPS chỉ trỏ tới AWS | Hostname HTTPS có cơ chế chuyển sang Azure sau khi writer được xác nhận |
| Khi primary mất khả dụng | Chờ AWS/dịch vụ được khôi phục | Thực hiện fencing, promote Azure và chuyển traffic theo runbook |
| Cost proxy | Tài nguyên phục vụ cấu hình AWS-only | Tài nguyên hai cloud và kết nối phục vụ warm standby |

Tái sử dụng cùng Terraform AWS, image, schema và cấu hình ứng dụng của project. Baseline là một chế độ triển khai/thí nghiệm, không phải một web hoặc kiến trúc code mới. Giữ cấu hình AWS tương đương giữa A/B; ghi rõ phần replication và dịch vụ dự phòng chỉ có ở B.

### 4.2. Kịch bản và điều kiện đo được đề xuất

Các bước dưới đây là thiết kế thí nghiệm dự kiến, chưa phải kết quả đã đo hoặc yêu cầu số lượng run của đề bài:

1. Chuẩn bị cùng dữ liệu khởi đầu, image digest, tài nguyên AWS, nguồn client đo và workload tạo/đọc issue. Client/probe đặt ngoài hai môi trường ứng dụng. Xác nhận writer và trạng thái hệ thống đúng trước mỗi lượt; B cần standby streaming khỏe.
2. Đo steady state trước lỗi, rồi gây cùng một lỗi mất môi trường primary bằng cách stop EC2 AWS tại mốc đã định. Chốt trước cửa sổ quan sát và lịch cho phép khôi phục AWS, ví dụ giữ stopped 120 giây từ lúc xác nhận stopped rồi cho phép start; dùng cùng chính sách cho A/B và lưu cả thời điểm gọi API lẫn các chuyển trạng thái thực tế.
3. A phục hồi trên AWS theo lịch và runbook; B thực hiện failover sang Azure sau khi xác nhận fencing. Khi AWS ở B được bật lại, giữ writer cũ bị chặn và làm rejoin theo runbook; việc máy running trở lại không cho phép bật writer cũ song song. Ghi rõ failover ở run là thủ công hay tự động; nếu thủ công, lưu mốc can thiệp của người vận hành.
4. Đo thành công của thao tác ghi/đọc từ phía client, không chỉ process liveness. Lưu downtime, recovery/failover time phù hợp, latency, request lỗi và kiểm chứng các write đã được ACK còn tồn tại sau phục hồi.
5. Đề xuất lặp năm lượt cho mỗi cấu hình, reset về trạng thái bắt đầu đã xác định sau mỗi lượt. Tổng hợp các run và dữ liệu thô; nếu không phục hồi trong cửa sổ đo, ghi rõ downtime ít nhất bằng khoảng đã quan sát và recovery time chưa xác định, không ghi một con số phục hồi giả.

Với A, cột failover time là N/A; thời gian phục hồi tại AWS và downtime vẫn đo được. Với B, đo thêm timeline phát hiện lỗi, fencing, promote, writer-ready và client phục hồi qua hostname. Không giả định trước B nhanh hơn hoặc không mất dữ liệu; kết luận dựa vào số đo và điều kiện thực tế.

Chi phí phải dùng cùng khoảng thời gian và phạm vi: compute-hours nhân đơn giá tương ứng, disk, public IP và traffic liên quan; xác định rõ có tính DNS và hệ đo chung hay không. Nếu giữ Azure disk/IP khi chạy baseline dù VM đã deallocate, phần chi phí giữ lab vẫn thuộc chi phí thực tế và phải ghi riêng. Cost proxy của kiến trúc AWS-only là mô hình so sánh, không được trình bày thành hóa đơn thực tế khi vẫn giữ tài nguyên ngoài cấu hình đó.

Script tạo lỗi, workload, reset và tính chỉ số sẽ được viết khi bắt đầu giai đoạn 9; chưa tạo thêm file hướng dẫn giai đoạn 9 trong bước xác định phạm vi này. Nguyên tắc đo từ phía người dùng, quan sát lỗi và phục hồi có thể tham chiếu [AWS resiliency testing](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_testing_resiliency_failure_injection_resiliency.html).

### 4.3. Quy ước chỉ số

Các quy ước cần chốt trong giai đoạn đo đạc:

- **Failover time:** xác định mốc bắt đầu/kết thúc; tách phát hiện lỗi, điều khiển failover và thời điểm client nhận dịch vụ phục hồi khi cần.
- **Downtime:** đo từ phía client, ghi tiêu chí thành công và cách xử lý request lỗi/timeout. Với workload ghi dữ liệu, kiểm tra khả năng ghi thành công thay vì chỉ liveness.
- **Latency:** ghi đơn vị, workload, mức tải và phân bố kết quả, chẳng hạn median/p95 khi phù hợp; đối chiếu trước lỗi và sau phục hồi.
- **Simple cost proxy:** dùng giờ chạy và đơn giá từng cloud, cộng disk/public IP trong cùng cửa sổ; ghi phạm vi, giả định và các hạng mục chưa tính. Có thể dùng VM-hours như chỉ số đơn giản nếu nêu rõ giới hạn do khác cấu hình/đơn giá.
- **Khả năng lặp lại:** lưu cấu hình, định danh image, tham số tải, các mốc thời gian, log và kết quả thô cho từng run. Phân biệt ví dụ tính toán với số đo đã thu thập.

RPO/mất acknowledged writes, replication lag, split-brain prevention, rejoin và failback là nội dung kỹ thuật bổ sung quan trọng cho hệ PostgreSQL stateful đã chọn. Chúng hỗ trợ phân tích consistency và vận hành; không thay thế bốn chỉ số được nêu ở S4.

## 5. Đối chiếu với lộ trình triển khai

| Giai đoạn | Đóng góp chính vào yêu cầu |
|---|---|
| 1. Ứng dụng/database local | Workload, replication và recovery có thể kiểm tra trước khi triển khai cloud |
| 2. Container packaging | Cùng artifact ứng dụng và cấu hình runtime riêng cho từng môi trường |
| 3. CI/container registry | Kiểm thử, phát hành và xác minh image; hỗ trợ reproducibility |
| 4. Hạ tầng AWS/Azure | Hai môi trường hạ tầng độc lập, chuẩn bị S1 và G1 |
| 5. Cluster/workload | Hai bản triển khai thực tế, kiểm tra ứng dụng và replication; S1 |
| 6. DNS/HTTPS | Đường truy cập người dùng và writer health cho traffic failover |
| 7. Failover/recovery | Fencing, promote, chuyển traffic, khôi phục; S2, S3 và S5 |
| 8. Monitoring | Quan sát độc lập và tín hiệu phục vụ S2/S4 |
| 9. Thí nghiệm/baseline/cost | G3-G6, bốn chỉ số S4 và phân tích trade-off S5 |
| 10. Report/demo | Tổng hợp G1-G7 và bằng chứng nghiệm thu |

Các phần hướng dẫn theo giai đoạn chỉ được bổ sung khi bắt đầu giai đoạn đó. Tài liệu yêu cầu này giữ phạm vi tham chiếu toàn project, không phải tuyên bố đã triển khai hoặc đo xong các giai đoạn sau.

### 5.1. Quy mô node và phạm vi high availability

Đề tài 29 và General Deliverables trong PDF yêu cầu hai môi trường hoặc cluster độc lập, không quy định ba node cho mỗi cluster. Hướng dẫn triển khai bổ sung của học phần có nội dung "Deploy a multi-node cloud service". Project diễn giải yêu cầu này ở cấp dịch vụ phân tán: một VM AWS và một VM Azure là hai máy độc lập, cùng tham gia hệ thống ứng dụng/database và cơ chế phục hồi. Đây là diễn giải phạm vi triển khai, không phải xác nhận rằng mỗi Kubernetes cluster đã đáp ứng một yêu cầu multi-node riêng. Nếu tiêu chí nghiệm thu được làm rõ là mỗi cluster Kubernetes phải multi-node, cần điều chỉnh topology trước triển khai tương ứng.

Thiết kế hiện tại dùng một K3s server node cho mỗi cloud. K3s hỗ trợ single-node cluster chạy đầy đủ control plane và workload. Mục tiêu được kiểm chứng là phục hồi dịch vụ khi mất toàn bộ một môi trường; từng cluster hiện có một điểm lỗi tại VM đó và không có control-plane HA nội bộ. Giới hạn này cần được nêu rõ trong kiến trúc, báo cáo và phân tích trade-off.

Nếu mở rộng sang K3s control-plane HA bằng embedded etcd, cần tối thiểu ba server node trong mỗi cluster. Một control plane cộng hai worker không tạo control-plane HA. Việc tăng số node cũng không tự hoàn thành thiết kế HA cho PostgreSQL và persistent storage; các phần đó cần được xem xét riêng. Chỉ mở rộng khi phạm vi đồ án yêu cầu hoặc cần thêm thí nghiệm so sánh.

Tham khảo kỹ thuật: [K3s single-node cluster](https://docs.k3s.io/quick-start), [K3s embedded etcd HA](https://docs.k3s.io/datastore/ha-embedded).

## 6. Trạng thái nghiệm thu hiện tại

- Local application/database, container packaging và CI/registry đã có kết quả kiểm tra trong hướng dẫn giai đoạn 1-3.
- Hạ tầng AWS và Azure đã được triển khai và nghiệm thu độc lập qua status/agent checks, post-apply plan No changes và SSH/Ubuntu. Sau lượt dọn lab, hai môi trường đã được tạo lại để thực hành giai đoạn 5.
- AWS và Azure đã cài K3s v1.35.1+k3s1, nghiệm thu node Ready, các Pod hệ thống và StorageClass. WireGuard, PostgreSQL primary/standby, WAL streaming và cùng application image digest trên hai cloud đã được kiểm tra. HTTP xác nhận đúng môi trường, phiên bản và vai trò database.
- S1 đã có bằng chứng triển khai cùng ứng dụng trên hai môi trường độc lập. Danh sách issue, chi tiết, bình luận và lịch sử tạo/đóng/mở lại khớp nhau qua API AWS/Azure; người thực hành xác nhận Azure standby từ chối ghi bằng HTTP 409. Đầu ra giai đoạn 5 đã đạt, giai đoạn 6 bắt đầu DNS/HTTPS.
- Traffic failover cloud và tình huống mất hoàn toàn một môi trường được thực hiện trong giai đoạn phục hồi tiếp theo để nghiệm thu S2/S3.
- Chưa nghiệm thu baseline cloud, bộ số đo cloud lặp lại được, biểu đồ và phân tích kết quả. Bảng giá/công thức hiện có là chuẩn bị cost proxy.
- Báo cáo cuối kỳ và demo tổng thể chưa hoàn thành.

Trước khi kết thúc một giai đoạn, đối chiếu đầu ra với S1-S5, G1-G7 và rubric; ghi bằng chứng đã có và phần còn thiếu. Xem [lộ trình triển khai](ROADMAP.md) và [hướng dẫn theo giai đoạn](instruction/).
