# -*- coding: utf-8 -*-

from . import models
from . import controllers
from . import lib

from eagle.api import Environment, SUPERUSER_ID


def uninstall_hook(cr, registry):
    env = Environment(cr, SUPERUSER_ID, {})
    for rec in env['eagle_dashboard.board'].search([]):
        rec.eagle_dashboard_client_action_id.unlink()
        rec.eagle_dashboard_menu_id.unlink()
