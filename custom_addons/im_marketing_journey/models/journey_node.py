from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ImJourneyNode(models.Model):
    """One step of a journey: wait, send a message, or branch."""

    _name = 'im.journey.node'
    _description = 'Marketing Journey Node'
    _order = 'sequence, id'

    journey_id = fields.Many2one('im.journey', string='Journey', required=True, ondelete='cascade')
    name = fields.Char(string='Node Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    node_type = fields.Selection([
        ('wait', 'Wait Delay'),
        ('action', 'Send Message (ZNS/Email)'),
        ('condition', 'Condition Branch'),
    ], string='Node Type', required=True, default='action')

    wait_duration = fields.Integer(string='Wait Duration', default=1)
    wait_unit = fields.Selection([
        ('hours', 'Hours'),
        ('days', 'Days'),
    ], string='Wait Unit', default='hours')

    action_type = fields.Selection([
        ('zns', 'Zalo ZNS'),
        ('email', 'Email'),
    ], string='Channel', default='zns')
    message_template = fields.Text(string='Message Content / Template')

    condition_type = fields.Selection([
        ('has_email', 'Valid Email Present'),
        ('has_phone', 'Phone Number Present'),
    ], string='Condition Type', default='has_phone')

    next_node_id = fields.Many2one(
        'im.journey.node', string='Next Node',
        domain="[('journey_id', '=', journey_id), ('id', '!=', id)]"
    )
    next_node_if_true_id = fields.Many2one(
        'im.journey.node', string='If TRUE -> Node',
        domain="[('journey_id', '=', journey_id), ('id', '!=', id)]"
    )
    next_node_if_false_id = fields.Many2one(
        'im.journey.node', string='If FALSE -> Node',
        domain="[('journey_id', '=', journey_id), ('id', '!=', id)]"
    )

    def _get_next_nodes(self):
        """Every outgoing edge of this node, whatever the node type."""
        self.ensure_one()
        return self.next_node_id | self.next_node_if_true_id | self.next_node_if_false_id

    @api.constrains('journey_id', 'next_node_id', 'next_node_if_true_id', 'next_node_if_false_id')
    def _check_next_nodes(self):
        """Edges must stay inside the journey, and must not loop."""
        for node in self:
            targets = node._get_next_nodes()

            outside = targets.filtered(lambda n: n.journey_id != node.journey_id)
            if outside:
                raise ValidationError(_(
                    "Node '%s' points to node(s) belonging to another journey: %s.\n"
                    "A participant would jump into a different scenario and receive the "
                    "wrong content."
                ) % (node.name, ', '.join(outside.mapped('name'))))

            if node in targets:
                raise ValidationError(_(
                    "Node '%s' points to itself."
                ) % node.name)

        for journey in self.journey_id:
            self._check_journey_has_no_cycle(journey)

    @api.model
    def _check_journey_has_no_cycle(self, journey):
        """Refuse a journey whose nodes loop back on themselves.

        Iterative DFS with the three-colour marking: an edge reaching a
        GREY node closes a cycle, and a participant inside it would never
        reach the end.
        """
        successors = {
            node.id: node._get_next_nodes().ids
            for node in journey.node_ids
        }
        names = {node.id: node.name for node in journey.node_ids}

        WHITE, GREY, BLACK = 0, 1, 2
        color = dict.fromkeys(successors, WHITE)

        for root in successors:
            if color[root] != WHITE:
                continue
            color[root] = GREY
            stack = [(root, iter(successors[root]))]
            while stack:
                node_id, pending = stack[-1]
                descended = False
                for next_id in pending:
                    if next_id not in color:
                        continue
                    if color[next_id] == GREY:
                        raise ValidationError(_(
                            "The nodes of journey '%s' form a loop (around '%s'). "
                            "A participant caught in it would never finish."
                        ) % (journey.name, names.get(next_id, next_id)))
                    if color[next_id] == WHITE:
                        color[next_id] = GREY
                        stack.append((next_id, iter(successors[next_id])))
                        descended = True
                        break
                if not descended:
                    color[node_id] = BLACK
                    stack.pop()
