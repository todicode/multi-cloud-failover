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

## 6. Trạng thái nghiệm thu hiện tại

- Local application/database, container packaging và CI/registry đã có kết quả kiểm tra trong hướng dẫn giai đoạn 1-3.
- AWS networking, Security Group và compute đã tạo; plan sau apply báo No changes, kết nối SSH chưa được nghiệm thu theo hướng dẫn giai đoạn 4.
- Chưa nghiệm thu S1 trên hai cloud thực tế, traffic failover cloud hoặc tình huống mất hoàn toàn một môi trường cloud.
- Chưa nghiệm thu baseline cloud, bộ số đo cloud lặp lại được, biểu đồ và phân tích kết quả. Bảng giá/công thức hiện có là chuẩn bị cost proxy.
- Báo cáo cuối kỳ và demo tổng thể chưa hoàn thành.

Trước khi kết thúc một giai đoạn, đối chiếu đầu ra với S1-S5, G1-G7 và rubric; ghi bằng chứng đã có và phần còn thiếu. Xem [lộ trình triển khai](ROADMAP.md) và [hướng dẫn theo giai đoạn](instruction/).
