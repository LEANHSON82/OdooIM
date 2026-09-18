from odoo import api, models


class SlideChannel(models.Model):
    """Hand im_elearning the mail templates this theme defines."""
    _inherit = 'slide.channel'

    @api.model
    def _im_get_mail_template(self, key):
        """Return this theme's template for *key*, else leave it to super().

        This is the only point where im_elearning and the theme meet.
        """
        template = self.env.ref(
            'im_theme.mail_template_%s' % key, raise_if_not_found=False)
        return template or super()._im_get_mail_template(key)
