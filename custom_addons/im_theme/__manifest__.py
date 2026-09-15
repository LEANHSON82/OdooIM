{
    'name': 'IM Theme',
    'version': '19.0.1.0.0',
    'category': 'Website/eLearning',
    'sequence': 106,
    'summary': 'Giao diện thư, chứng chỉ PDF và trang thi cho IM eLearning',
    'description': 'Phần nhìn thấy của IM eLearning, tách riêng khỏi logic.',
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
