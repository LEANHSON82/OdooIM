"""Remove the "Verify a certificate" entry from the website's main menu."""
MENU_URL = '/certificate/verify'


def migrate(cr, version):
    cr.execute("DELETE FROM website_menu WHERE url = %s", (MENU_URL,))
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module = 'im_elearning'
           AND name = 'website_menu_certificate_verify'
    """)
