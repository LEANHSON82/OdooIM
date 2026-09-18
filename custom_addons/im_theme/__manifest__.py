{
    'name': 'IM Theme',
    'version': '19.0.1.0.0',
    'category': 'Website/eLearning',
    'sequence': 106,
    'summary': 'Giao diện thư, chứng chỉ PDF và trang thi cho IM eLearning',
    'description': """
Phần nhìn thấy của IM eLearning: thư, chứng chỉ PDF, trang bắt đầu bài thi.

Tách riêng khỏi logic để sửa giao diện mà không đụng nghiệp vụ, và để thay bộ
mặt khác cho khách khác bằng cách thay module này.

Điểm nối: im_elearning gọi slide.channel._im_get_mail_template(key) với key là
certificate_issued, exam_failed, assignment_reminder hoặc assignment_overdue;
module này trả về mẫu thư tương ứng. Muốn làm theme khác thì kế thừa hàm đó.

Tự cài kèm im_elearning. Gỡ đi thì im_elearning vẫn chạy nhưng không gửi thư
và không in được chứng chỉ, log ghi rõ lý do.
Chi tiết: README.md trong module.
""",
    'author': 'IM',
    'license': 'LGPL-3',
    'depends': ['im_elearning'],
    'data': [
        'data/mail_layout.xml',
        'report/certificate_report.xml',
        'data/mail_template_data.xml',
        'views/survey_templates.xml',
        'views/survey_survey_views.xml',
    ],
    'assets': {
        # Exam page uses its own bundle
        'survey.survey_assets': [
            'im_theme/static/src/scss/survey.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': True,
}
