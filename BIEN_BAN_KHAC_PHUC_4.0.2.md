# Đối chiếu kiểm toán NBL LIVE 4.0.2

Ngày: 17/10/2026. Căn cứ: đầy đủ biên bản 19 mục người dùng cung cấp.
Giữ các tính năng của 4.0.1, sửa trực tiếp phần lỗi, không thay lại dự án.

**Kết luận:** đã sửa mã cho 18 mục lỗi và xử lý phần cấu hình/công cụ của M05.
M05 còn mở ở bước đo trên 20 ảnh Studio thật. Các kiểm tra trên Windows,
TikTok LIVE Studio, Chrome thật và phiên LIVE có người trông vẫn chưa thực hiện.
Không coi kết quả phát triển dưới đây là chứng nhận đủ điều kiện vận hành.

| Mã | Xử lý trong bản này | Bằng chứng / phần còn thiếu |
|---|---|---|
| C01 | Manifest đọc UTF-8; đầu ra kiểm tra UTF-8; rà các lệnh đọc văn bản khi chạy | Chạy chính check() với mặc định đọc cp1258 và cp1252 được ép trong test; cập nhật dùng checker thật. Chưa chạy OS Windows hai bảng mã |
| C02 | Báo động chạy `-ExecutionPolicy Bypass -File` và đường dẫn script thật | Test chính Alarm.scan(); kiểm cú pháp PowerShell; có cửa sổ thử Windows riêng nhưng chưa chạy UIA Windows |
| H01 | Tách CommandExpired trước input thành lỗi thử lại; unknown OCR trước input được hoãn; Dừng và cảnh báo thật giữ nguyên | Test hết hạn trước/sau input, token Dừng, OCR 0.6, lỗi thật, các trạng thái chức năng |
| H02 | Probe cập nhật đồng hồ nhưng giữ đệm cảnh báo 20 giây; quét cảnh báo mới trước input | Chạy đếm OCR: ba probe chỉ quét toàn cửa sổ một lần; thao tác yêu cầu mới thì quét lại |
| H03 | Dung sai nhỏ theo từ; giữ số/đơn vị/phủ định; chuẩn hóa tiền tệ; xóa draft chỉ khi còn đúng ảnh và đúng ô nhận phím | Test rn/m, ký hiệu tiền, giá khác, số khác, KHÔNG, draft người dùng đổi và đổi focus. Chưa bấm/xóa draft thật trên Windows |
| H04 | Một lần thử dừng; thất bại thì cho chọn đóng với cảnh báo LIVE có thể còn chạy; hủy tác vụ và lưu recovery_review | Chạy đường closeEvent thật được tách khỏi Qt cho ba nhánh và lỗi hàng đợi; Qt thật mở/đóng không có LIVE |
| M01 | Nhận cụm cảnh báo ở giữa nhãn ngắn; bỏ giới hạn loại control; vẫn loại chat/input; đếm ngược từ các nhãn toàn cửa sổ | Chạy biểu thức PowerShell thật trên các câu có tiền tố. Câu chữ/UIA Studio thật chưa kiểm chứng |
| M02 | Một hàm chuẩn hóa tên ở bước lưu và bước chạy; lệnh Chrome dùng tên chuẩn đã gắn của Chrome | Test tên hoa/thường/dấu và bảo vệ tên khác số; đọc lại mọi chỗ gửi expectedAccount |
| M03 | Bỏ trang trí emoji/ký hiệu khi so tác giả, giữ chữ/số và ranh giới tên | Test tên có emoji, tên khác số, tác giả cùng dòng; không nhận prefix Nick 1 thành Nick 12 |
| M04 | Dịch vụ OCR cùng tiến trình, loopback có mã ngẫu nhiên và quyền đọc trạng thái theo lượt ngắn; PowerShell không mở Python/nạp lại model | Test socket thật, xác thực, thu hồi lượt và hai lần gọi PowerShell thật đến cùng service. Chưa đo probe Windows |
| M05 | Giữ model có đủ chữ Việt; ép chiều rộng theo batch về 320/640; có benchmark offline và chống đếm ảnh trùng | OCR thật trên chữ giao diện mẫu đạt. **Chưa có 20 ảnh Studio thật có nhãn; mục này chưa đóng** |
| M06 | Sao lưu studio_schedules.json, giữ bản hỏng, khôi phục/cứu dữ liệu và hiện cảnh báo; không tự chạy lịch cũ từ backup | Test lưu/khôi phục/salvage và mở giao diện Qt thật với file hỏng |
| M07 | Lượt cũ giữ uncertain nếu chưa rõ; ghi confirmed_after_stop khi thực sự có xác nhận, not_sent khi biết chưa gửi | Test kết quả cũ không làm đổi lượt mới và không xóa mất tính chưa chắc |
| L01 | Thu hồi lệnh của tab mất; hết hạn, gộp lệnh dừng trùng, không chờ đủ 2.5 giây khi tab đã mất | Test 600 lệnh và mất tab; flush trả chưa xác nhận, không thành công giả |
| L02 | Ghi nhớ lỗi nạp OCR 60 giây; tệp thay đổi được thử lại sớm | Test hai lần gọi model hỏng chỉ khởi tạo một lần |
| L03 | Dùng similar có giới hạn trong so chữ; bỏ shuffled_order và cfg không dùng | Quét mã, hồi quy từ khóa/playlist/ghim giữ nguyên |
| L04 | Test cập nhật chép và chạy checker thật bằng Python thật; không dùng checker pass | Test thành công/lặp/khôi phục và test codec ở chính check() |
| L05 | requirements-test, run_tests.py, TEST_RESULT.json ghi phụ thuộc/bỏ qua/thất bại thật | Lượt cuối 103 Python + 17 JS, không bỏ qua. Môi trường và giới hạn bên dưới |
| L06 | Ghi rõ 16 phiên/nguồn video khác tối đa 2 hồ sơ Studio | Hướng dẫn sử dụng mới; không mở rộng số nick |

## Kết quả đã chạy

- 103 bài Python đạt, không bỏ qua; 17 bài JavaScript đạt.
- Chạy OCR thật với RapidOCR 1.4.4 và model kèm gói; đây là ảnh chữ mẫu, không phải 20 ảnh Studio thật.
- Chạy PowerShell 7.4.6 trên Linux: bộ lọc, máy khách OCR, sao lưu/khôi phục và checker thật.
- Chạy Qt 6.12.0 offscreen trên Linux: mở/đóng và khôi phục tệp lịch hỏng.
- Chạy WebSocket/loopback thật; không mở phiên TikTok hay gửi bình luận thật.
- Mọi tệp PowerShell được phân tích cú pháp; chưa chạy Windows PowerShell 5.1/UI Automation.
- TEST_RESULT.json và KET_QUA_KIEM_TRA.txt chứa thông tin và nhật ký thực tế.

## Chưa đủ bằng chứng để nghiệm thu vận hành

1. Cập nhật trên Windows thật cp1258/cp1252; bước UI Automation bằng cửa sổ thử.
2. 20 ảnh Studio thật có nhãn và đo thời gian status/gửi trên máy Windows vận hành.
3. Phiên LIVE có người trông: nhắn, Chào, ghim, trả lời và kết thúc theo lịch.
4. Hai nick đồng thời, OBS, video và âm thanh thực tế trên máy đó.

Không thay ảnh mẫu, đối tượng giả, số assertion hoặc số lần chạy lặp thành số
bài nghiệm thu thực tế. Không có chức năng né xác minh hay bảo đảm tránh vi phạm.
