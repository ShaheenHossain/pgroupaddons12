# -*- coding: utf-8 -*-

from eagle import models, fields, api, _
from eagle.exceptions import UserError, ValidationError


class KsDashboardNinjaBoardItemAction(models.TransientModel):
    _name = 'eagle_ninja_dashboard.item_action'
    _description = 'Eagle Dashboard Item Actions'

    name = fields.Char()
    eagle_dashboard_item_ids = fields.Many2many("eagle_dashboard.item", string="Dashboard Items")
    eagle_action = fields.Selection([('move', 'Move'),
                                  ('duplicate', 'Duplicate'),
                                  ], string="Action")
    eagle_dashboard_id = fields.Many2one("eagle_dashboard.board", string="Select Dashboard")
    eagle_dashboard_ids = fields.Many2many("eagle_dashboard.board", string="Select Dashboards")

    # Move or Copy item to another dashboard action
    @api.multi
    def action_item_move_copy_action(self):
        if self.eagle_action == 'move':
            for item in self.eagle_dashboard_item_ids:
                item.eagle_dashboard_board_id = self.eagle_dashboard_id
        elif self.eagle_action == 'duplicate':
            # Using sudo here to allow creating same item without any security error
            for dashboard_id in self.eagle_dashboard_ids:
                for item in self.eagle_dashboard_item_ids:
                    item.sudo().copy({'eagle_dashboard_board_id': dashboard_id.id})
