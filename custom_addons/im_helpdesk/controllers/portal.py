"""Portal routes for IM Helpdesk.

This controller lets customers list, create, read and close helpdesk tickets from the
website portal, while still checking team visibility and access tokens the way the Odoo
portal framework expects.
"""

from operator import itemgetter

from markupsafe import Markup

from odoo import http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.fields import Domain
from odoo.http import request
from odoo.tools import consteq, groupby as groupbyelem, plaintext2html
from odoo.tools.translate import _
from odoo.addons.portal.controllers import portal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class CustomerPortal(portal.CustomerPortal):
    """Extend the standard portal with the helpdesk ticket pages."""

    def _prepare_portal_layout_values(self):
        """Return the layout values shared by the portal pages.

        For now this only calls the parent implementation; it is kept as a local
        hook so helpdesk-specific layout values are easy to add later.
        """
        values = super()._prepare_portal_layout_values()
        return values

    def _prepare_home_portal_values(self, counters):
        """Add the ticket counter shown on the portal home page."""
        values = super()._prepare_home_portal_values(counters)
        if 'ticket_count' in counters:
            values['ticket_count'] = (
                request.env['helpdesk.ticket'].search_count(self._prepare_helpdesk_tickets_domain())
                if request.env['helpdesk.ticket'].has_access('read')
                else 0
            )
        return values

    def _prepare_helpdesk_tickets_domain(self):
        """Build the base ticket domain the current portal user may read.

        A portal user only sees tickets of a public team when they are the
        customer or a follower. Internal users keep the unrestricted behaviour
        of the parent portal and need no extra domain.
        """
        if request.env.user._is_portal():
            partner = request.env.user.partner_id
            return [
                ('team_privacy_visibility', '=', 'portal'),
                '|',
                    ('partner_id', '=', partner.id),
                    ('message_partner_ids', 'in', [partner.id]),
            ]
        return []

    def _portal_can_access_ticket(self, ticket, access_token=None):
        """Check whether the current request may open one given ticket.

        A valid access token always grants access to the ticket URL. Without a
        token, the portal user has to be the ticket customer or one of its
        followers.
        """
        if access_token and ticket.access_token and consteq(ticket.access_token, access_token):
            return True
        if not request.env.user._is_portal():
            return True
        partner = request.env.user.partner_id
        return bool(partner and (ticket.partner_id == partner or partner in ticket.message_partner_ids))

    def _get_portal_ticket_teams(self):
        """Return the active public teams that accept tickets from the portal."""
        return request.env['helpdesk.team'].sudo().search([
            ('active', '=', True),
            ('privacy_visibility', '=', 'portal'),
            ('company_id', 'in', request.env.companies.ids or [request.env.company.id]),
        ])

    def _prepare_portal_create_ticket_values(self, error=None, post=None):
        """Prepare the template values for the portal ticket form."""
        partner = request.env.user.partner_id
        teams = self._get_portal_ticket_teams()
        return {
            **self._prepare_portal_layout_values(),
            'page_name': 'ticket_create',
            'teams': teams,
            'default_team_id': int(post.get('team_id')) if post and str(post.get('team_id', '')).isdigit() else (teams[:1].id or False),
            'partner': partner,
            'error': error,
            'post': post or {},
        }

    def _ticket_get_page_view_values(self, ticket, access_token, **kwargs):
        """Prepare the template values for one ticket detail page."""
        values = {
            'page_name': 'ticket',
            'ticket': ticket,
            'ticket_link_section': [],
            'ticket_closed': kwargs.get('ticket_closed', False),
            'preview_object': ticket,
            'res_company': ticket.company_id
        }
        return self._get_page_view_values(ticket, access_token, values, 'my_tickets_history', False, **kwargs)

    def _ticket_get_searchbar_inputs(self):
        """Return the fields that can be searched in the portal ticket list."""
        return {
            'name': {'input': 'name', 'label': _(
                'Search%(left)s Tickets%(right)s',
                left=Markup('<span class="nolabel">'),
                right=Markup('</span>'),
            ), 'sequence': 10},
            'user_id': {'input': 'user_id', 'label': _('Search in Assigned to'), 'sequence': 20},
            'partner_id': {'input': 'partner_id', 'label': _('Search in Customer'), 'sequence': 30},
            'team_id': {'input': 'team_id', 'label': _('Search in Helpdesk Team'), 'sequence': 40},
            'stage_id': {'input': 'stage_id', 'label': _('Search in Stage'), 'sequence': 50},
        }

    def _ticket_get_searchbar_groupby(self):
        """Return the group-by choices offered in the portal ticket list."""
        return {
            'none': {'label': _('None'), 'sequence': 10},
            'user_id': {'label': _('Assigned to'), 'sequence': 20},
            'team_id': {'label': _('Helpdesk Team'), 'sequence': 30},
            'stage_id': {'label': _('Stage'), 'sequence': 40},
            'kanban_state': {'label': _('Status'), 'sequence': 50},
            'partner_id': {'label': _('Customer'), 'sequence': 60},
        }

    def _ticket_get_search_domain(self, search_in, search):
        """Turn the portal search input into an ORM domain."""
        if search_in == 'name':
            return ['|', ('name', 'ilike', search), ('ticket_ref', 'ilike', search)]
        elif search_in == 'user_id':
            assignees = request.env['res.users'].sudo()._search([('name', 'ilike', search)])
            return [('user_id', 'in', assignees)]
        elif search_in in self._ticket_get_searchbar_inputs():
            return [(search_in, 'ilike', search)]
        else:
            return ['|', ('name', 'ilike', search), ('ticket_ref', 'ilike', search)]

    def _prepare_my_tickets_values(self, page=1, date_begin=None, date_end=None, sortby=None, filterby='all', search=None, groupby='none', search_in='name'):
        """Prepare the paginated portal ticket list.

        Filtering, sorting, grouping, searching and pager state all live here,
        so the route itself only has to render the final template.
        """
        values = self._prepare_portal_layout_values()
        domain = Domain(self._prepare_helpdesk_tickets_domain())

        searchbar_sortings = {
            'id desc': {'label': _('Newest')},
            'name': {'label': _('Subject')},
            'user_id': {'label': _('Assigned to')},
            'stage_id': {'label': _('Stage')},
            'date_last_stage_update desc': {'label': _('Last Stage Update')},
        }
        searchbar_filters = {
            'all': {'label': _('All'), 'domain': []},
            'assigned': {'label': _('Assigned'), 'domain': [('user_id', '!=', False)]},
            'unassigned': {'label': _('Unassigned'), 'domain': [('user_id', '=', False)]},
            'open': {'label': _('Open'), 'domain': [('close_date', '=', False)]},
            'closed': {'label': _('Closed'), 'domain': [('close_date', '!=', False)]},
        }
        searchbar_inputs = dict(sorted(self._ticket_get_searchbar_inputs().items(), key=lambda item: item[1]['sequence']))
        searchbar_groupby = dict(sorted(self._ticket_get_searchbar_groupby().items(), key=lambda item: item[1]['sequence']))

        if not sortby:
            sortby = next(iter(searchbar_sortings))

        domain &= Domain(searchbar_filters[filterby]['domain'])

        if date_begin and date_end:
            domain &= Domain('create_date', '>', date_begin) & Domain('create_date', '<=', date_end)

        if search and search_in:
            domain &= Domain(self._ticket_get_search_domain(search_in, search))

        tickets_count = request.env['helpdesk.ticket'].search_count(domain)
        pager = portal_pager(
            url="/my/tickets",
            url_args={'date_begin': date_begin, 'date_end': date_end, 'sortby': sortby, 'search_in': search_in, 'search': search, 'groupby': groupby, 'filterby': filterby},
            total=tickets_count,
            page=page,
            step=self._items_per_page
        )

        order = f'{groupby}, {sortby}' if groupby != 'none' else sortby
        tickets = request.env['helpdesk.ticket'].search(domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['my_tickets_history'] = tickets.ids[:100]

        if not tickets:
            grouped_tickets = []
        elif groupby != 'none':
            grouped_tickets = [request.env['helpdesk.ticket'].concat(*g) for k, g in groupbyelem(tickets, itemgetter(groupby))]
        else:
            grouped_tickets = [tickets]

        values.update({
            'date': date_begin,
            'grouped_tickets': grouped_tickets,
            'page_name': 'ticket',
            'default_url': '/my/tickets',
            'pager': pager,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': searchbar_filters,
            'searchbar_inputs': searchbar_inputs,
            'searchbar_groupby': searchbar_groupby,
            'sortby': sortby,
            'groupby': groupby,
            'search_in': search_in,
            'search': search,
            'filterby': filterby,
        })
        return values

    @http.route(['/my/tickets', '/my/tickets/page/<int:page>'], type='http', auth="user", website=True)
    def my_helpdesk_tickets(self, page=1, date_begin=None, date_end=None, sortby=None, filterby='all', search=None, groupby='none', search_in='name', **kw):
        """Render the portal ticket list of the current user."""
        values = self._prepare_my_tickets_values(page, date_begin, date_end, sortby, filterby, search, groupby, search_in)
        return request.render("im_helpdesk.portal_helpdesk_ticket", values)

    @http.route(['/my/tickets/new'], type='http', auth="user", website=True)
    def my_helpdesk_ticket_new(self, **kw):
        """Render the ticket creation form on the portal."""
        values = self._prepare_portal_create_ticket_values(post=kw)
        return request.render("im_helpdesk.portal_create_ticket", values)

    @http.route(['/my/tickets/create'], type='http', auth="user", website=True, methods=['POST'])
    def my_helpdesk_ticket_create(self, **post):
        """Validate the portal form and create the helpdesk ticket.

        Creation runs in sudo because a portal user usually cannot write every
        backend field directly. The new ticket is still tied to the portal
        partner and stays protected by the access token generated for it.
        """
        teams = self._get_portal_ticket_teams()
        team_id = post.get('team_id')
        selected_team_id = int(team_id) if team_id and str(team_id).isdigit() else False
        team = teams.filtered(lambda portal_team: portal_team.id == selected_team_id)[:1] if selected_team_id else teams[:1]

        name = (post.get('name') or '').strip()
        description = (post.get('description') or '').strip()
        phone = (post.get('phone') or '').strip()

        error = None
        if not teams:
            error = _("No public helpdesk team is available. Please contact an administrator.")
        elif not name:
            error = _("Ticket subject is required.")
        elif not team:
            error = _("Please select a valid helpdesk team.")

        if error:
            values = self._prepare_portal_create_ticket_values(error=error, post=post)
            return request.render("im_helpdesk.portal_create_ticket", values)

        partner = request.env.user.partner_id
        ticket = request.env['helpdesk.ticket'].sudo().create({
            'name': name,
            'team_id': team.id,
            'description': plaintext2html(description) if description else False,
            'partner_id': partner.id,
            'partner_name': partner.name,
            'partner_email': partner.email,
            'partner_phone': phone or partner.phone,
        })
        if partner:
            ticket.message_subscribe(partner_ids=partner.ids)
        ticket._portal_ensure_token()

        return request.redirect('/my/ticket/%s/%s' % (ticket.id, ticket.access_token))

    @http.route([
        "/helpdesk/ticket/<int:ticket_id>",
        "/helpdesk/ticket/<int:ticket_id>/<access_token>",
        '/my/ticket/<int:ticket_id>',
        '/my/ticket/<int:ticket_id>/<access_token>'
    ], type='http', auth="public", website=True)
    def tickets_followup(self, ticket_id=None, access_token=None, **kw):
        """Render the ticket follow-up page once token and follower are checked."""
        try:
            ticket_sudo = self._document_check_access('helpdesk.ticket', ticket_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if not self._portal_can_access_ticket(ticket_sudo, access_token=access_token):
            return request.redirect('/my')

        values = self._ticket_get_page_view_values(ticket_sudo, access_token, **kw)
        return request.render("im_helpdesk.tickets_followup", values)

    @http.route([
        '/my/ticket/close/<int:ticket_id>',
        '/my/ticket/close/<int:ticket_id>/<access_token>',
    ], type='http', auth="public", website=True)
    def ticket_close(self, ticket_id=None, access_token=None, **kw):
        """Close a ticket from the portal when the team allows it.

        This route accepts both a public link carrying a token and a logged-in
        portal user. It moves the ticket to the team closing stage, records that
        the customer closed it and posts an internal note for the audit trail.
        """
        try:
            ticket_sudo = self._document_check_access('helpdesk.ticket', ticket_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')

        if not self._portal_can_access_ticket(ticket_sudo, access_token=access_token):
            return request.redirect('/my')

        if not ticket_sudo.team_id.allow_portal_ticket_closing:
            raise UserError(_("The team does not allow ticket closing through portal"))

        if not ticket_sudo.closed_by_partner and request.httprequest.method == 'GET':
            closing_stage = ticket_sudo.team_id._get_closing_stage()
            if ticket_sudo.stage_id != closing_stage:
                ticket_vals = {'stage_id': closing_stage[0].id, 'closed_by_partner': True}
                if request.env.user._is_public():
                    ticket_sudo.write(ticket_vals)
                else:
                    ticket_sudo.with_user(request.env.user).sudo().write(ticket_vals)
            else:
                ticket_sudo.write({'closed_by_partner': True})
            body = _('Ticket closed by the customer')

            author_id = None
            if request.env.user._is_public() and ticket_sudo.partner_id:
                author_id = ticket_sudo.partner_id.id
            elif not request.env.user._is_public() and request.env.user.partner_id:
                author_id = request.env.user.partner_id.id

            ticket_sudo.with_context(mail_post_autofollow_author_skip=True).message_post(
                body=body,
                message_type='comment',
                subtype_xmlid='mail.mt_note',
                author_id=author_id
            )

        return request.redirect('/my/ticket/%s/%s?ticket_closed=1' % (ticket_id, access_token or ''))
