from odoo import models, fields, api

from odoo.addons.product.models.product_template import PRICE_CONTEXT_KEYS

class EventTicket(models.Model):
    _inherit = 'event.event.ticket'

    is_early_bird = fields.Boolean(string='Is Early Bird Ticket', default=False)
    early_bird_deadline = fields.Datetime(string='Early Bird Deadline')
    early_bird_max_qty = fields.Integer(string='Early Bird Max Quantity', default=0)
    early_bird_sold_qty = fields.Integer(
        string='Early Bird Sold Quantity',
        compute='_compute_early_bird_sold_qty',
        store=True
    )
    price_early_bird = fields.Float(string='Early Bird Price')
    price_standard = fields.Float(string='Standard Price')
    is_early_bird_active = fields.Boolean(
        string='Early Bird Active',
        compute='_compute_is_early_bird_active',
        store=True
    )

    @api.depends('registration_ids.state', 'registration_ids.is_early_bird_sale')
    def _compute_early_bird_sold_qty(self):
        for ticket in self:
            ticket.early_bird_sold_qty = len(
                ticket.registration_ids.filtered(
                    lambda r: r.state != 'cancel' and r.is_early_bird_sale
                )
            )

    def _is_early_bird_now(self, extra_sold=0):
        """Early-bird is over once the deadline passes or seats run out.

        `extra_sold` covers registrations created in the same batch that
        are not stored yet.
        """
        self.ensure_one()
        if not self.is_early_bird:
            return False
        if self.early_bird_deadline and self.early_bird_deadline < fields.Datetime.now():
            return False
        if self.early_bird_max_qty > 0 and self.early_bird_sold_qty + extra_sold >= self.early_bird_max_qty:
            return False
        return True

    def _get_early_bird_price(self):
        self.ensure_one()
        if not self.is_early_bird:
            return None
        if self._is_early_bird_now() and self.price_early_bird:
            return self.price_early_bird
        if self.price_standard:
            return self.price_standard
        return None

    @api.depends('is_early_bird', 'early_bird_deadline', 'early_bird_max_qty', 'early_bird_sold_qty')
    def _compute_is_early_bird_active(self):
        for ticket in self:
            ticket.is_early_bird_active = ticket._is_early_bird_now()

    @api.depends('product_id', 'is_early_bird', 'early_bird_deadline', 'early_bird_max_qty',
                 'price_early_bird', 'price_standard')
    def _compute_price(self):
        # super() runs on the non early-bird subset only. Calling it on
        # self would reset our two-tier prices back to the product price.
        fallback = self.browse()
        for ticket in self:
            target = ticket._get_early_bird_price()
            if target is None:
                fallback |= ticket
            else:
                ticket.price = target
        if fallback:
            super(EventTicket, fallback)._compute_price()

    @api.depends_context(*PRICE_CONTEXT_KEYS)
    @api.depends('product_id', 'price', 'is_early_bird', 'early_bird_deadline',
                 'early_bird_max_qty', 'early_bird_sold_qty', 'price_early_bird', 'price_standard')
    def _compute_price_reduce(self):
        super()._compute_price_reduce()
        for ticket in self:
            target = ticket._get_early_bird_price()
            if target is None:
                continue
            discount = ticket.product_id._get_contextual_discount()
            ticket.price_reduce = (1.0 - discount) * target

    @api.model
    def _cron_refresh_early_bird(self):
        """Recompute early-bird prices; nothing fires when a deadline passes."""
        tickets = self.search([('is_early_bird', '=', True)])
        if not tickets:
            return
        for field_name in ('is_early_bird_active', 'price'):
            self.env.add_to_compute(self._fields[field_name], tickets)
        tickets.flush_recordset()
