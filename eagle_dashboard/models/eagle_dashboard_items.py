# -*- coding: utf-8 -*-
import dateutil
import datetime as dt
import pytz
import json
import babel

from eagle.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT
from eagle.tools.safe_eval import safe_eval
from collections import defaultdict
from datetime import datetime
from dateutil import relativedelta
from eagle import models, fields, api, _
from eagle.exceptions import ValidationError, UserError
from eagle.addons.eagle_dashboard.lib.eagle_date_filter_selections import eagle_get_date

# TODO : Check all imports if needed


read = fields.Many2one.read


def eagle_read(self, records):
    if self.name == 'eagle_list_view_fields' or self.name == 'eagle_list_view_group_fields':
        comodel = records.env[self.comodel_name]

        # String domains are supposed to be dynamic and evaluated on client-side
        # only (thus ignored here).
        domain = self.domain if isinstance(self.domain, list) else []

        wquery = comodel._where_calc(domain)
        comodel._apply_ir_rules(wquery, 'read')
        from_c, where_c, where_params = wquery.get_sql()
        query = """ SELECT {rel}.{id1}, {rel}.{id2} FROM {rel}, {from_c}
                    WHERE {where_c} AND {rel}.{id1} IN %s AND {rel}.{id2} = {tbl}.id
                """.format(rel=self.relation, id1=self.column1, id2=self.column2,
                           tbl=comodel._table, from_c=from_c, where_c=where_c or '1=1',
                           limit=(' LIMIT %d' % self.limit) if self.limit else '',
                           )
        where_params.append(tuple(records.ids))

        # retrieve lines and group them by record
        group = defaultdict(list)
        records._cr.execute(query, where_params)
        rec_list = records._cr.fetchall()
        for row in rec_list:
            group[row[0]].append(row[1])

        # store result in cache
        cache = records.env.cache
        for record in records:
            if self.name == 'eagle_list_view_fields':
                field = 'eagle_list_view_fields'
            else:
                field = 'eagle_list_view_group_fields'
            order = False
            if record.eagle_many2many_field_ordering:
                order = json.loads(record.eagle_many2many_field_ordering).get(field, False)

            if order:
                group[record.id].sort(key=lambda x: order.index(x))
            cache.set(record, self, tuple(group[record.id]))

    else:
        comodel = records.env[self.comodel_name]

        # String domains are supposed to be dynamic and evaluated on client-side
        # only (thus ignored here).
        domain = self.domain if isinstance(self.domain, list) else []

        wquery = comodel._where_calc(domain)
        comodel._apply_ir_rules(wquery, 'read')
        order_by = comodel._generate_order_by(None, wquery)
        from_c, where_c, where_params = wquery.get_sql()
        query = """ SELECT {rel}.{id1}, {rel}.{id2} FROM {rel}, {from_c}
                           WHERE {where_c} AND {rel}.{id1} IN %s AND {rel}.{id2} = {tbl}.id
                           {order_by} {limit} OFFSET {offset}
                       """.format(rel=self.relation, id1=self.column1, id2=self.column2,
                                  tbl=comodel._table, from_c=from_c, where_c=where_c or '1=1',
                                  limit=(' LIMIT %d' % self.limit) if self.limit else '',
                                  offset=0, order_by=order_by)
        where_params.append(tuple(records.ids))

        # retrieve lines and group them by record
        group = defaultdict(list)
        records._cr.execute(query, where_params)
        for row in records._cr.fetchall():
            group[row[0]].append(row[1])

        # store result in cache
        cache = records.env.cache
        for record in records:
            cache.set(record, self, tuple(group[record.id]))


fields.Many2many.read = eagle_read

read_group = models.BaseModel._read_group_process_groupby


def eagle_time_addition(self, gb, query):
    """
        Overwriting default to add minutes to Helper method to collect important
        information about groupbys: raw field name, type, time information, qualified name, ...
    """
    split = gb.split(':')
    field_type = self._fields[split[0]].type
    gb_function = split[1] if len(split) == 2 else None
    temporal = field_type in ('date', 'datetime')
    tz_convert = field_type == 'datetime' and self._context.get('tz') in pytz.all_timezones
    qualified_field = self._inherits_join_calc(self._table, split[0], query)
    if temporal:
        display_formats = {
            'minute': 'hh:mm dd MMM',
            'hour': 'hh:00 dd MMM',
            'day': 'dd MMM yyyy',  # yyyy = normal year
            'week': "'W'w YYYY",  # w YYYY = ISO week-year
            'month': 'MMMM yyyy',
            'quarter': 'QQQ yyyy',
            'year': 'yyyy',
        }
        time_intervals = {
            'minute': dateutil.relativedelta.relativedelta(minutes=1),
            'hour': dateutil.relativedelta.relativedelta(hours=1),
            'day': dateutil.relativedelta.relativedelta(days=1),
            'week': dt.timedelta(days=7),
            'month': dateutil.relativedelta.relativedelta(months=1),
            'quarter': dateutil.relativedelta.relativedelta(months=3),
            'year': dateutil.relativedelta.relativedelta(years=1)
        }
        if tz_convert:
            qualified_field = "timezone('%s', timezone('UTC',%s))" % (self._context.get('tz', 'UTC'), qualified_field)
        qualified_field = "date_trunc('%s', %s::timestamp)" % (gb_function or 'month', qualified_field)
    if field_type == 'boolean':
        qualified_field = "coalesce(%s,false)" % qualified_field
    return {
        'field': split[0],
        'groupby': gb,
        'type': field_type,
        'display_format': display_formats[gb_function or 'month'] if temporal else None,
        'interval': time_intervals[gb_function or 'month'] if temporal else None,
        'tz_convert': tz_convert,
        'qualified_field': qualified_field,
    }


models.BaseModel._read_group_process_groupby = eagle_time_addition


class KsDashboardNinjaItems(models.Model):
    _name = 'eagle_dashboard.item'
    _description = 'Eagle Dashboard items'

    name = fields.Char(string="Name", size=256)
    eagle_model_id = fields.Many2one('ir.model', string='Model',
                                  domain="[('access_ids','!=',False),('transient','=',False),"
                                         "('model','not ilike','base_import%'),('model','not ilike','ir.%'),"
                                         "('model','not ilike','web_editor.%'),('model','not ilike','web_tour.%'),"
                                         "('model','!=','mail.thread'),('model','not ilike','eagle_dash%')]")
    eagle_domain = fields.Char(string="Domain")

    eagle_model_id_2 = fields.Many2one('ir.model', string='Kpi Model',
                                    domain="[('access_ids','!=',False),('transient','=',False),"
                                           "('model','not ilike','base_import%'),('model','not ilike','ir.%'),"
                                           "('model','not ilike','web_editor.%'),('model','not ilike','web_tour.%'),"
                                           "('model','!=','mail.thread'),('model','not ilike','eagle_dash%')]")

    eagle_model_name_2 = fields.Char(related='eagle_model_id_2.model', string="Kpi Model Name")

    # This field main purpose is to store %UID as current user id. Mainly used in JS file as container.
    eagle_domain_temp = fields.Char(string="Domain Substitute")
    eagle_background_color = fields.Char(string="Background Color",
                                      default="#ffffff,0.99")
    eagle_icon = fields.Binary(string="Upload Icon", attachment=True)
    eagle_default_icon = fields.Char(string="Icon", default="bar-chart")
    eagle_default_icon_color = fields.Char(default="#ffffff,0.99", string="Icon Color")
    eagle_icon_select = fields.Char(string="Icon Option", default="Default")
    eagle_font_color = fields.Char(default="#ffffff,0.99", string="Font Color")
    eagle_dashboard_item_theme = fields.Char(string="Theme", default="white")
    eagle_layout = fields.Selection([('layout1', 'Layout 1'),
                                  ('layout2', 'Layout 2'),
                                  ('layout3', 'Layout 3'),
                                  ('layout4', 'Layout 4'),
                                  ('layout5', 'Layout 5'),
                                  ('layout6', 'Layout 6'),
                                  ], default=('layout1'), required=True, string="Layout")
    eagle_preview = fields.Integer(default=1, string="Preview")
    eagle_model_name = fields.Char(related='eagle_model_id.model', string="Model Name")

    eagle_record_count_type_2 = fields.Selection([('count', 'Count'),
                                               ('sum', 'Sum'),
                                               ('average', 'Average')], string="Kpi Record Type", default="sum")
    eagle_record_field_2 = fields.Many2one('ir.model.fields',
                                        domain="[('model_id','=',eagle_model_id_2),('name','!=','id'),('store','=',True),"
                                               "'|','|',('ttype','=','integer'),('ttype','=','float'),"
                                               "('ttype','=','monetary')]",
                                        string="Kpi Record Field")
    eagle_record_count_2 = fields.Float(string="KPI Record Count", readonly=True, compute='eagle_get_record_count_2')
    eagle_record_count_type = fields.Selection([('count', 'Count'),
                                             ('sum', 'Sum'),
                                             ('average', 'Average')], string="Record Type", default="count")
    eagle_record_count = fields.Float(string="Record Count", compute='eagle_get_record_count', readonly=True)
    eagle_record_field = fields.Many2one('ir.model.fields',
                                      domain="[('model_id','=',eagle_model_id),('name','!=','id'),('store','=',True),'|',"
                                             "'|',('ttype','=','integer'),('ttype','=','float'),"
                                             "('ttype','=','monetary')]",
                                      string="Record Field")

    # Date Filter Fields
    # Condition to tell if date filter is applied or not
    eagle_isDateFilterApplied = fields.Boolean(default=False)

    # ---------------------------- Date Filter Fields ------------------------------------------
    eagle_date_filter_field = fields.Many2one('ir.model.fields',
                                           domain="[('model_id','=',eagle_model_id),'|',('ttype','=','date'),"
                                                  "('ttype','=','datetime')]",
                                           string="Date Filter Field")
    eagle_date_filter_selection = fields.Selection([
        ('l_none', 'None'),
        ('l_day', 'Today'),
        ('t_week', 'This Week'),
        ('t_month', 'This Month'),
        ('t_quarter', 'This Quarter'),
        ('t_year', 'This Year'),
        ('n_day', 'Next Day'),
        ('n_week', 'Next Week'),
        ('n_month', 'Next Month'),
        ('n_quarter', 'Next Quarter'),
        ('n_year', 'Next Year'),
        ('ls_day', 'Last Day'),
        ('ls_week', 'Last Week'),
        ('ls_month', 'Last Month'),
        ('ls_quarter', 'Last Quarter'),
        ('ls_year', 'Last Year'),
        ('l_week', 'Last 7 days'),
        ('l_month', 'Last 30 days'),
        ('l_quarter', 'Last 90 days'),
        ('l_year', 'Last 365 days'),
        ('l_custom', 'Custom Filter'),
    ], string="Date Filter Selection", default="l_none", required=True)

    eagle_item_start_date = fields.Datetime(string="Start Date")
    eagle_item_end_date = fields.Datetime(string="End Date")

    eagle_date_filter_field_2 = fields.Many2one('ir.model.fields',
                                             domain="[('model_id','=',eagle_model_id_2),'|',('ttype','=','date'),"
                                                    "('ttype','=','datetime')]",
                                             string="Kpi Date Filter Field")

    eagle_item_start_date_2 = fields.Datetime(string="Kpi Start Date")
    eagle_item_end_date_2 = fields.Datetime(string="Kpi End Date")

    eagle_domain_2 = fields.Char(string="Kpi Domain")
    eagle_domain_2_temp = fields.Char(string="Kpi Domain Substitute")

    eagle_date_filter_selection_2 = fields.Selection([
        ('l_none', "None"),
        ('l_day', 'Today'),
        ('t_week', 'This Week'),
        ('t_month', 'This Month'),
        ('t_quarter', 'This Quarter'),
        ('t_year', 'This Year'),
        ('n_day', 'Next Day'),
        ('n_week', 'Next Week'),
        ('n_month', 'Next Month'),
        ('n_quarter', 'Next Quarter'),
        ('n_year', 'Next Year'),
        ('ls_day', 'Last Day'),
        ('ls_week', 'Last Week'),
        ('ls_month', 'Last Month'),
        ('ls_quarter', 'Last Quarter'),
        ('ls_year', 'Last Year'),
        ('l_week', 'Last 7 days'),
        ('l_month', 'Last 30 days'),
        ('l_quarter', 'Last 90 days'),
        ('l_year', 'Last 365 days'),
        ('l_custom', 'Custom Filter'),
    ], string="Kpi Date Filter Selection", required=True, default='l_none')

    eagle_previous_period = fields.Boolean(string="Previous Period")

    # ------------------------ Pro Fields --------------------
    eagle_dashboard_board_id = fields.Many2one('eagle_dashboard.board', string="Dashboard",
                                                  default=lambda self: self._context[
                                                    'eagle_dashboard_id'] if 'eagle_dashboard_id' in self._context else False)

    # Chart related fields
    eagle_dashboard_item_type = fields.Selection([('eagle_tile', 'Tile'),
                                               ('eagle_bar_chart', 'Bar Chart'),
                                               ('eagle_horizontalBar_chart', 'Horizontal Bar Chart'),
                                               ('eagle_line_chart', 'Line Chart'),
                                               ('eagle_area_chart', 'Area Chart'),
                                               ('eagle_pie_chart', 'Pie Chart'),
                                               ('eagle_doughnut_chart', 'Doughnut Chart'),
                                               ('eagle_polarArea_chart', 'Polar Area Chart'),
                                               ('eagle_list_view', 'List View'),
                                               ('eagle_kpi', 'KPI')
                                               ], default=lambda self: self._context.get('eagle_dashboard_item_type',
                                                                                         'eagle_tile'), required=True,
                                              string="Dashboard Item Type")
    eagle_chart_groupby_type = fields.Char(compute='get_chart_groupby_type')
    eagle_chart_sub_groupby_type = fields.Char(compute='get_chart_sub_groupby_type')
    eagle_chart_relation_groupby = fields.Many2one('ir.model.fields',
                                                domain="[('model_id','=',eagle_model_id),('name','!=','id'),"
                                                       "('store','=',True),('ttype','!=','binary'),"
                                                       "('ttype','!=','many2many'), ('ttype','!=','one2many')]",
                                                string="Group By")
    eagle_chart_relation_sub_groupby = fields.Many2one('ir.model.fields',
                                                    domain="[('model_id','=',eagle_model_id),('name','!=','id'),"
                                                           "('store','=',True),('ttype','!=','binary'),"
                                                           "('ttype','!=','many2many'), ('ttype','!=','one2many')]",
                                                    string=" Sub Group By")
    eagle_chart_date_groupby = fields.Selection([('minute', 'Minute'),
                                              ('hour', 'Hour'),
                                              ('day', 'Day'),
                                              ('week', 'Week'),
                                              ('month', 'Month'),
                                              ('quarter', 'Quarter'),
                                              ('year', 'Year'),
                                              ], string="Dashboard Item Chart Group By Type")
    eagle_chart_date_sub_groupby = fields.Selection([('minute', 'Minute'),
                                                  ('hour', 'Hour'),
                                                  ('day', 'Day'),
                                                  ('week', 'Week'),
                                                  ('month', 'Month'),
                                                  ('quarter', 'Quarter'),
                                                  ('year', 'Year'),
                                                  ], string="Dashboard Item Chart Sub Group By Type")
    eagle_graph_preview = fields.Char(string="Graph Preview", default="Graph Preview")
    eagle_chart_data = fields.Char(string="Chart Data in string form", compute='eagle_get_chart_data')
    eagle_chart_data_count_type = fields.Selection([('count', 'Count'), ('sum', 'Sum'), ('average', 'Average')],
                                                string="Data Type", default="sum")
    eagle_chart_measure_field = fields.Many2many('ir.model.fields', 'eagle_dn_measure_field_rel', 'measure_field_id',
                                              'field_id',
                                              domain="[('model_id','=',eagle_model_id),('name','!=','id'),"
                                                     "('store','=',True),'|','|',"
                                                     "('ttype','=','integer'),('ttype','=','float'),"
                                                     "('ttype','=','monetary')]",
                                              string="Measure 1")

    eagle_chart_measure_field_2 = fields.Many2many('ir.model.fields', 'eagle_dn_measure_field_rel_2', 'measure_field_id_2',
                                                'field_id',
                                                domain="[('model_id','=',eagle_model_id),('name','!=','id'),"
                                                       "('store','=',True),'|','|',"
                                                       "('ttype','=','integer'),('ttype','=','float'),"
                                                       "('ttype','=','monetary')]",
                                                string="Line Measure")

    eagle_bar_chart_stacked = fields.Boolean(string="Stacked Bar Chart")

    eagle_semi_circle_chart = fields.Boolean(string="Semi Circle Chart")

    eagle_sort_by_field = fields.Many2one('ir.model.fields',
                                       domain="[('model_id','=',eagle_model_id),('name','!=','id'),('store','=',True),"
                                              "('ttype','!=','one2many'),('ttype','!=','many2one'),"
                                              "('ttype','!=','binary')]",
                                       string="Sort By Field")
    eagle_sort_by_order = fields.Selection([('ASC', 'Ascending'), ('DESC', 'Descending')],
                                        string="Sort Order")
    eagle_record_data_limit = fields.Integer(string="Record Limit")

    eagle_list_view_preview = fields.Char(string="List View Preview", default="List View Preview")

    eagle_kpi_preview = fields.Char(string="Kpi Preview", default="KPI Preview")

    eagle_kpi_type = fields.Selection([
        ('layout_1', 'KPI With Target'),
        ('layout_2', 'Data Comparison'),
    ], string="Kpi Layout", default="layout_1")

    eagle_target_view = fields.Char(string="View", default="Number")

    eagle_data_comparison = fields.Char(string="Kpi Data Type", default="None")

    eagle_kpi_data = fields.Char(string="KPI Data", compute="eagle_get_kpi_data")

    eagle_chart_item_color = fields.Selection(
        [('default', 'Default'), ('cool', 'Cool'), ('warm', 'Warm'), ('neon', 'Neon')],
        string="Chart Color Palette", default="default")

    # ------------------------ List View Fields ------------------------------

    eagle_list_view_type = fields.Selection([('ungrouped', 'Un-Grouped'), ('grouped', 'Grouped')], default="ungrouped",
                                         string="List View Type", required=True)
    eagle_list_view_fields = fields.Many2many('ir.model.fields', 'eagle_dn_list_field_rel', 'list_field_id', 'field_id',
                                           domain="[('model_id','=',eagle_model_id),('ttype','!=','one2many'),"
                                                  "('ttype','!=','many2many'),('ttype','!=','binary')]",
                                           string="Fields to show in list")

    eagle_list_view_group_fields = fields.Many2many('ir.model.fields', 'eagle_dn_list_group_field_rel', 'list_field_id',
                                                 'field_id',
                                                 domain="[('model_id','=',eagle_model_id),('name','!=','id'),"
                                                        "('store','=',True),'|','|',"
                                                        "('ttype','=','integer'),('ttype','=','float'),"
                                                        "('ttype','=','monetary')]",
                                                 string="List View Grouped Fields")

    eagle_list_view_data = fields.Char(string="List View Data in JSon", compute='eagle_get_list_view_data')

    # -------------------- Multi Company Feature ---------------------
    eagle_company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id)

    # -------------------- Target Company Feature ---------------------
    eagle_goal_enable = fields.Boolean(string="Enable Target")
    eagle_goal_bar_line = fields.Boolean(string="Show Target As Line")
    eagle_standard_goal_value = fields.Float(string="Standard Target")
    eagle_goal_lines = fields.One2many('eagle_dashboard.item_goal', 'eagle_dashboard_item', string="Target Lines")

    eagle_list_target_deviation_field = fields.Many2one('ir.model.fields', 'list_field_id',
                                                     domain="[('model_id','=',eagle_model_id),('name','!=','id'),"
                                                            "('store','=',True),'|','|',"
                                                            "('ttype','=','integer'),('ttype','=','float'),"
                                                            "('ttype','=','monetary')]",
                                                     )

    eagle_many2many_field_ordering = fields.Char()

    # TODO : Merge all these fields into one and show a widget to get output for these fields from JS
    eagle_show_data_value = fields.Boolean(string="Show Data Value")

    eagle_action_lines = fields.One2many('eagle_dashboard.item_action', 'eagle_dashboard_item_id', string="Action Lines")

    eagle_actions = fields.Many2one('ir.actions.act_window', domain="[('res_model','=',eagle_model_name)]",
                                 string="Actions", help="This Action will be Performed at the end of Drill Down Action")

    eagle_compare_period = fields.Integer(string="Include Period")
    eagle_year_period = fields.Integer(string="Same Period Previous Years")
    eagle_compare_period_2 = fields.Integer(string="Include Period")
    eagle_year_period_2 = fields.Integer(string="Same Period Previous Years")

    # Adding refresh per item override global update interval
    eagle_update_items_data = fields.Selection([
        (15000, '15 Seconds'),
        (30000, '30 Seconds'),
        (45000, '45 Seconds'),
        (60000, '1 minute'),
        (120000, '2 minute'),
        (300000, '5 minute'),
        (600000, '10 minute'),
    ], string="Item Update Interval", default=lambda self: self._context.get('eagle_set_interval', False))

    # User can select custom units for measure
    eagle_unit = fields.Boolean(string="Show Custom Unit", default=False)
    eagle_unit_selection = fields.Selection([
        ('monetary', 'Monetary'),
        ('custom', 'Custom'),
    ], string="Select Unit Type")
    eagle_chart_unit = fields.Char(string="Enter Unit", size=5, default="",
                                help="Maximum limit 5 characters, for ex: km, m")

    # User can stop propagation of the tile item
    eagle_show_records = fields.Boolean(string="Show Records", default=True, help="""This field Enable the click on 
                                                                                  Dashboard Items to view the Eagle 
                                                                                  default view of records""")
    eagle_data_calculation_type = fields.Selection([('custom', 'Custom'),
                                                 ('query', 'Query')], string="Data Calculation Type", default="custom")


    @api.onchange('eagle_goal_lines')
    def eagle_date_target_line(self):
        for rec in self:
            if rec.eagle_chart_date_groupby in ('minute', 'hour') or rec.eagle_chart_date_sub_groupby in ('minute', 'hour'):
                rec.eagle_goal_lines = False
                return {'warning': {
                    'title': _('Groupby Field aggregation'),
                    'message': _(
                        'Cannot create target lines when Group By Date field is set to have aggregation in '
                        'Minute and Hour case.')
                }}

    @api.multi
    @api.onchange('eagle_chart_date_groupby', 'eagle_chart_date_sub_groupby')
    def eagle_date_target(self):
        for rec in self:
            if (rec.eagle_chart_date_groupby in ('minute', 'hour') or rec.eagle_chart_date_sub_groupby in ('minute', 'hour'))\
                    and rec.eagle_goal_lines:
                raise ValidationError(_(
                    "Cannot set aggregation having Date time (Hour, Minute) when target lines per date are being used."
                    " To proceed this, first delete target lines"))

    @api.multi
    def copy_data(self, default=None):
        if default is None:
            default = {}
        if 'eagle_action_lines' not in default:
            default['eagle_action_lines'] = [(0, 0, line.copy_data()[0]) for line in self.eagle_action_lines]

        if 'eagle_goal_lines' not in default:
            default['eagle_goal_lines'] = [(0, 0, line.copy_data()[0]) for line in self.eagle_goal_lines]

        return super(KsDashboardNinjaItems, self).copy_data(default)

    @api.multi
    def name_get(self):
        res = []
        for rec in self:
            name = rec.name
            if not name:
                name = rec.eagle_model_id.name
            res.append((rec.id, name))

        return res

    @api.model
    def create(self, values):
        """ Override to save list view fields ordering """
        if values.get('eagle_list_view_fields', False) and values.get('eagle_list_view_group_fields', False):
            eagle_many2many_field_ordering = {
                'eagle_list_view_fields': values['eagle_list_view_fields'][0][2],
                'eagle_list_view_group_fields': values['eagle_list_view_group_fields'][0][2],
            }
            values['eagle_many2many_field_ordering'] = json.dumps(eagle_many2many_field_ordering)

        return super(KsDashboardNinjaItems, self).create(
            values)

    @api.multi
    def write(self, values):
        for rec in self:
            if rec['eagle_many2many_field_ordering']:
                eagle_many2many_field_ordering = json.loads(rec['eagle_many2many_field_ordering'])
            else:
                eagle_many2many_field_ordering = {}
            if values.get('eagle_list_view_fields', False):
                eagle_many2many_field_ordering['eagle_list_view_fields'] = values['eagle_list_view_fields'][0][2]
            if values.get('eagle_list_view_group_fields', False):
                eagle_many2many_field_ordering['eagle_list_view_group_fields'] = values['eagle_list_view_group_fields'][0][2]
            values['eagle_many2many_field_ordering'] = json.dumps(eagle_many2many_field_ordering)

        return super(KsDashboardNinjaItems, self).write(
            values)

    @api.onchange('eagle_list_view_fields')
    def eagle_set_list_view_fields_order(self):
        for rec in self:
            order = [res.id for res in rec.eagle_list_view_fields]
            if rec.eagle_many2many_field_ordering:
                eagle_many2many_field_ordering = json.loads(rec.eagle_many2many_field_ordering)
            else:
                eagle_many2many_field_ordering = {}
            eagle_many2many_field_ordering['eagle_list_view_fields'] = order
            rec.eagle_many2many_field_ordering = json.dumps(eagle_many2many_field_ordering)

    @api.onchange('eagle_list_view_group_fields')
    def eagle_set_list_view_group_fields_order(self):
        for rec in self:
            order = [res.id for res in rec.eagle_list_view_group_fields]
            if rec.eagle_many2many_field_ordering:
                eagle_many2many_field_ordering = json.loads(rec.eagle_many2many_field_ordering)
            else:
                eagle_many2many_field_ordering = {}
            eagle_many2many_field_ordering['eagle_list_view_group_fields'] = order
            rec.eagle_many2many_field_ordering = json.dumps(eagle_many2many_field_ordering)

    @api.onchange('eagle_layout')
    def layout_four_font_change(self):
        if self.eagle_dashboard_item_theme != "white":
            if self.eagle_layout == 'layout4':
                self.eagle_font_color = self.eagle_background_color
                self.eagle_default_icon_color = "#ffffff,0.99"
            elif self.eagle_layout == 'layout6':
                self.eagle_font_color = "#ffffff,0.99"
                self.eagle_default_icon_color = self.eagle_get_dark_color(self.eagle_background_color.split(',')[0],
                                                                    self.eagle_background_color.split(',')[1])
            else:
                self.eagle_default_icon_color = "#ffffff,0.99"
                self.eagle_font_color = "#ffffff,0.99"
        else:
            if self.eagle_layout == 'layout4':
                self.eagle_background_color = "#00000,0.99"
                self.eagle_font_color = self.eagle_background_color
                self.eagle_default_icon_color = "#ffffff,0.99"
            else:
                self.eagle_background_color = "#ffffff,0.99"
                self.eagle_font_color = "#00000,0.99"
                self.eagle_default_icon_color = "#00000,0.99"

    # To convert color into 10% darker. Percentage amount is hardcoded. Change amt if want to change percentage.
    def eagle_get_dark_color(self, color, opacity):
        num = int(color[1:], 16)
        amt = -25
        R = (num >> 16) + amt
        R = (255 if R > 255 else 0 if R < 0 else R) * 0x10000
        G = (num >> 8 & 0x00FF) + amt
        G = (255 if G > 255 else 0 if G < 0 else G) * 0x100
        B = (num & 0x0000FF) + amt
        B = (255 if B > 255 else 0 if B < 0 else B)
        return "#" + hex(0x1000000 + R + G + B).split('x')[1][1:] + "," + opacity

    @api.onchange('eagle_model_id')
    def make_record_field_empty(self):
        for rec in self:
            rec.eagle_record_field = False
            rec.eagle_domain = False
            rec.eagle_date_filter_field = False
            # To show "created on" by default on date filter field on model select.
            if rec.eagle_model_id:
                datetime_field_list = rec.eagle_date_filter_field.search(
                    [('model_id', '=', rec.eagle_model_id.id), '|', ('ttype', '=', 'date'),
                     ('ttype', '=', 'datetime')]).read(['id', 'name'])
                for field in datetime_field_list:
                    if field['name'] == 'create_date':
                        rec.eagle_date_filter_field = field['id']
            else:
                rec.eagle_date_filter_field = False
            # Pro
            rec.eagle_record_field = False
            rec.eagle_chart_measure_field = False
            rec.eagle_chart_measure_field_2 = False
            rec.eagle_chart_relation_sub_groupby = False
            rec.eagle_chart_relation_groupby = False
            rec.eagle_chart_date_sub_groupby = False
            rec.eagle_chart_date_groupby = False
            rec.eagle_sort_by_field = False
            rec.eagle_sort_by_order = False
            rec.eagle_record_data_limit = False
            rec.eagle_list_view_fields = False
            rec.eagle_list_view_group_fields = False
            rec.eagle_action_lines = False
            rec.eagle_actions   = False

    @api.onchange('eagle_record_count', 'eagle_layout', 'name', 'eagle_model_id', 'eagle_domain', 'eagle_icon_select',
                  'eagle_default_icon', 'eagle_icon',
                  'eagle_background_color', 'eagle_font_color', 'eagle_default_icon_color')
    def eagle_preview_update(self):
        self.eagle_preview += 1

    @api.onchange('eagle_dashboard_item_theme')
    def change_dashboard_item_theme(self):
        if self.eagle_dashboard_item_theme == "red":
            self.eagle_background_color = "#d9534f,0.99"
            self.eagle_default_icon_color = "#ffffff,0.99"
            self.eagle_font_color = "#ffffff,0.99"
        elif self.eagle_dashboard_item_theme == "blue":
            self.eagle_background_color = "#337ab7,0.99"
            self.eagle_default_icon_color = "#ffffff,0.99"
            self.eagle_font_color = "#ffffff,0.99"
        elif self.eagle_dashboard_item_theme == "yellow":
            self.eagle_background_color = "#f0ad4e,0.99"
            self.eagle_default_icon_color = "#ffffff,0.99"
            self.eagle_font_color = "#ffffff,0.99"
        elif self.eagle_dashboard_item_theme == "green":
            self.eagle_background_color = "#5cb85c,0.99"
            self.eagle_default_icon_color = "#ffffff,0.99"
            self.eagle_font_color = "#ffffff,0.99"
        elif self.eagle_dashboard_item_theme == "white":
            if self.eagle_layout == 'layout4':
                self.eagle_background_color = "#00000,0.99"
                self.eagle_default_icon_color = "#ffffff,0.99"
            else:
                self.eagle_background_color = "#ffffff,0.99"
                self.eagle_default_icon_color = "#000000,0.99"
                self.eagle_font_color = "#000000,0.99"

        if self.eagle_layout == 'layout4':
            self.eagle_font_color = self.eagle_background_color

        elif self.eagle_layout == 'layout6':
            self.eagle_default_icon_color = self.eagle_get_dark_color(self.eagle_background_color.split(',')[0],
                                                                self.eagle_background_color.split(',')[1])
            if self.eagle_dashboard_item_theme == "white":
                self.eagle_default_icon_color = "#000000,0.99"

    @api.multi
    @api.depends('eagle_record_count_type', 'eagle_model_id', 'eagle_domain', 'eagle_record_field', 'eagle_date_filter_field',
                 'eagle_item_end_date', 'eagle_item_start_date', 'eagle_compare_period', 'eagle_year_period',
                 'eagle_dashboard_item_type')
    def eagle_get_record_count(self):
        for rec in self:
            if rec.eagle_record_count_type == 'count' or rec.eagle_dashboard_item_type == 'eagle_list_view':
                rec.eagle_record_count = rec.eagle_fetch_model_data(rec.eagle_model_name, rec.eagle_domain, 'search_count', rec)
            elif rec.eagle_record_count_type in ['sum', 'average'] and rec.eagle_record_field and  rec.eagle_dashboard_item_type != 'eagle_list_view':
                eagle_records_grouped_data = rec.eagle_fetch_model_data(rec.eagle_model_name, rec.eagle_domain, 'read_group', rec)
                if eagle_records_grouped_data and len(eagle_records_grouped_data) > 0:
                    eagle_records_grouped_data = eagle_records_grouped_data[0]
                    if rec.eagle_record_count_type == 'sum' and eagle_records_grouped_data.get('__count', False) and (
                            eagle_records_grouped_data.get(rec.eagle_record_field.name)):
                        rec.eagle_record_count = eagle_records_grouped_data.get(rec.eagle_record_field.name, 0)
                    elif rec.eagle_record_count_type == 'average' and eagle_records_grouped_data.get(
                            '__count', False) and (eagle_records_grouped_data.get(rec.eagle_record_field.name)):
                        rec.eagle_record_count = eagle_records_grouped_data.get(rec.eagle_record_field.name,
                                                                          0) / eagle_records_grouped_data.get('__count',
                                                                                                           1)
                    else:
                        rec.eagle_record_count = 0
                else:
                    rec.eagle_record_count = 0
            else:
                rec.eagle_record_count = 0

    # Writing separate function to fetch dashboard item data
    def eagle_fetch_model_data(self, eagle_model_name, eagle_domain, eagle_func, rec):
        data = 0
        try:
            if eagle_domain and eagle_domain != '[]' and eagle_model_name:
                proper_domain = self.eagle_convert_into_proper_domain(eagle_domain, rec)
                if eagle_func == 'search_count':
                    data = self.env[eagle_model_name].search_count(proper_domain)
                elif eagle_func == 'read_group':
                    data = self.env[eagle_model_name].read_group(proper_domain, [rec.eagle_record_field.name], [])
            elif eagle_model_name:
                # Have to put extra if condition here because on load,model giving False value
                proper_domain = self.eagle_convert_into_proper_domain(False, rec)
                if eagle_func == 'search_count':
                    data = self.env[eagle_model_name].search_count(proper_domain)

                elif eagle_func == 'read_group':
                    data = self.env[eagle_model_name].read_group(proper_domain, [rec.eagle_record_field.name], [])
            else:
                return []
        except Exception as e:
            return []
        return data

    def eagle_convert_into_proper_domain(self, eagle_domain, rec):
        if eagle_domain and "%UID" in eagle_domain:
            eagle_domain = eagle_domain.replace('"%UID"', str(self.env.user.id))

        if eagle_domain and "%MYCOMPANY" in eagle_domain:
            eagle_domain = eagle_domain.replace('"%MYCOMPANY"', str(self.env.user.company_id.id))

        eagle_date_domain = False

        if not rec.eagle_date_filter_selection or rec.eagle_date_filter_selection == "l_none":
            selected_start_date = self._context.get('ksDateFilterStartDate', False)
            selected_end_date = self._context.get('ksDateFilterEndDate', False)
            if selected_start_date and selected_end_date and rec.eagle_date_filter_field.name:
                eagle_date_domain = [
                    (rec.eagle_date_filter_field.name, ">=", selected_start_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT)),
                    (rec.eagle_date_filter_field.name, "<=", selected_end_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT))]
        else:
            if rec.eagle_date_filter_selection and rec.eagle_date_filter_selection != 'l_custom':
                eagle_date_data = eagle_get_date(rec.eagle_date_filter_selection)
                selected_start_date = eagle_date_data["selected_start_date"]
                selected_end_date = eagle_date_data["selected_end_date"]
            else:
                if rec.eagle_item_start_date or rec.eagle_item_end_date:
                    selected_start_date = rec.eagle_item_start_date
                    selected_end_date = rec.eagle_item_end_date

            if selected_start_date and selected_end_date and rec.eagle_date_filter_field:
                if rec.eagle_compare_period:
                    eagle_compare_period = abs(rec.eagle_compare_period)
                    if eagle_compare_period > 100:
                        eagle_compare_period = 100
                    if rec.eagle_compare_period > 0:
                        selected_end_date = selected_end_date + (
                                selected_end_date - selected_start_date) * eagle_compare_period
                    elif rec.eagle_compare_period < 0:
                        selected_start_date = selected_start_date - (
                                selected_end_date - selected_start_date) * eagle_compare_period

                if rec.eagle_year_period and rec.eagle_year_period != 0 and rec.eagle_dashboard_item_type:
                    abs_year_period = abs(rec.eagle_year_period)
                    sign_yp = rec.eagle_year_period / abs_year_period
                    if abs_year_period > 10:
                        abs_year_period = 10
                    date_field_name = rec.eagle_date_filter_field.name

                    eagle_date_domain = ['&', (date_field_name, ">=", fields.datetime.strftime(selected_start_date,
                                                                                            DEFAULT_SERVER_DATETIME_FORMAT)),
                                      (date_field_name, "<=",
                                       fields.datetime.strftime(selected_end_date, DEFAULT_SERVER_DATETIME_FORMAT))]

                    for p in range(1, abs_year_period + 1):
                        eagle_date_domain.insert(0, '|')
                        eagle_date_domain.extend(['&', (date_field_name, ">=", fields.datetime.strftime(
                            selected_start_date - relativedelta.relativedelta(years=p) * sign_yp,
                            DEFAULT_SERVER_DATETIME_FORMAT)),
                                               (date_field_name, "<=", fields.datetime.strftime(
                                                   selected_end_date - relativedelta.relativedelta(years=p) * sign_yp,
                                                   DEFAULT_SERVER_DATETIME_FORMAT))])
                else:
                    if rec.eagle_date_filter_field:
                        selected_start_date = fields.datetime.strftime(selected_start_date, DEFAULT_SERVER_DATETIME_FORMAT)
                        selected_end_date = fields.datetime.strftime(selected_end_date, DEFAULT_SERVER_DATETIME_FORMAT)
                        eagle_date_domain = [(rec.eagle_date_filter_field.name, ">=", selected_start_date),
                                      (rec.eagle_date_filter_field.name, "<=", selected_end_date)]
                    else:
                        eagle_date_domain = []

        proper_domain = eval(eagle_domain) if eagle_domain else []
        if eagle_date_domain:
            proper_domain.extend(eagle_date_domain)


        return proper_domain

    @api.multi
    @api.onchange('eagle_chart_relation_groupby')
    def get_chart_groupby_type(self):
        for rec in self:
            if rec.eagle_chart_relation_groupby.ttype == 'datetime' or rec.eagle_chart_relation_groupby.ttype == 'date':
                rec.eagle_chart_groupby_type = 'date_type'
            elif rec.eagle_chart_relation_groupby.ttype == 'many2one':
                rec.eagle_chart_groupby_type = 'relational_type'
            elif rec.eagle_chart_relation_groupby.ttype == 'selection':
                rec.eagle_chart_groupby_type = 'selection'
            else:
                rec.eagle_chart_groupby_type = 'other'

    @api.onchange('eagle_chart_relation_groupby')
    def eagle_empty_sub_group_by(self):
        for rec in self:
            if not rec.eagle_chart_relation_groupby or rec.eagle_chart_groupby_type == "date_type" \
                    and not rec.eagle_chart_date_groupby:
                rec.eagle_chart_relation_sub_groupby = False
                rec.eagle_chart_date_sub_groupby = False

    @api.depends('eagle_chart_relation_sub_groupby')
    def get_chart_sub_groupby_type(self):
        for rec in self:
            if rec.eagle_chart_relation_sub_groupby.ttype == 'datetime' or \
                    rec.eagle_chart_relation_sub_groupby.ttype == 'date':
                rec.eagle_chart_sub_groupby_type = 'date_type'
            elif rec.eagle_chart_relation_sub_groupby.ttype == 'many2one':
                rec.eagle_chart_sub_groupby_type = 'relational_type'

            elif rec.eagle_chart_relation_sub_groupby.ttype == 'selection':
                rec.eagle_chart_sub_groupby_type = 'selection'

            else:
                rec.eagle_chart_sub_groupby_type = 'other'

    # Using this function just to let js call rpc to load some data later
    @api.model
    def eagle_chart_load(self):
        return True

    @api.multi
    @api.depends('eagle_chart_measure_field', 'eagle_chart_relation_groupby', 'eagle_chart_date_groupby', 'eagle_domain',
                 'eagle_dashboard_item_type', 'eagle_model_id', 'eagle_sort_by_field', 'eagle_sort_by_order',
                 'eagle_record_data_limit', 'eagle_chart_data_count_type', 'eagle_chart_measure_field_2', 'eagle_goal_enable',
                 'eagle_standard_goal_value', 'eagle_goal_bar_line', 'eagle_chart_relation_sub_groupby',
                 'eagle_chart_date_sub_groupby', 'eagle_date_filter_field', 'eagle_item_start_date', 'eagle_item_end_date',
                 'eagle_compare_period', 'eagle_year_period', 'eagle_unit', 'eagle_unit_selection', 'eagle_chart_unit')
    def eagle_get_chart_data(self):
        for rec in self:


            if rec.eagle_dashboard_item_type and rec.eagle_dashboard_item_type != 'eagle_tile' and \
                    rec.eagle_dashboard_item_type != 'eagle_list_view' and rec.eagle_model_id and rec.eagle_chart_data_count_type:
                eagle_chart_data = {'labels': [], 'datasets': [], 'eagle_currency': 0, 'eagle_field': "", 'eagle_selection': "", 'eagle_show_second_y_scale': False, 'domains': [], }
                eagle_chart_measure_field = []
                eagle_chart_measure_field_ids = []
                eagle_chart_measure_field_2 = []
                eagle_chart_measure_field_2_ids = []

                if rec.eagle_unit and rec.eagle_unit_selection == 'monetary':
                    eagle_chart_data['eagle_selection'] += rec.eagle_unit_selection
                    eagle_chart_data['eagle_currency'] += rec.env.user.company_id.currency_id.id
                elif rec.eagle_unit and rec.eagle_unit_selection == 'custom':
                    eagle_chart_data['eagle_selection'] += rec.eagle_unit_selection
                    if rec.eagle_chart_unit:
                        eagle_chart_data['eagle_field'] += rec.eagle_chart_unit

                # If count chart data type:
                if rec.eagle_chart_data_count_type == "count":
                    eagle_chart_data['datasets'].append({'data': [], 'label': "Count"})
                else:
                    if rec.eagle_dashboard_item_type == 'eagle_bar_chart':
                        if rec.eagle_chart_measure_field_2:
                            eagle_chart_data['eagle_show_second_y_scale'] = True

                        for res in rec.eagle_chart_measure_field_2:
                            eagle_chart_measure_field_2.append(res.name)
                            eagle_chart_measure_field_2_ids.append(res.id)
                            eagle_chart_data['datasets'].append(
                                {'data': [], 'label': res.field_description, 'type': 'line', 'yAxisID': 'y-axis-1'})

                    for res in rec.eagle_chart_measure_field:
                        eagle_chart_measure_field.append(res.name)
                        eagle_chart_measure_field_ids.append(res.id)
                        eagle_chart_data['datasets'].append({'data': [], 'label': res.field_description})


                # eagle_chart_measure_field = [res.name for res in rec.eagle_chart_measure_field]
                eagle_chart_groupby_relation_field = rec.eagle_chart_relation_groupby.name
                eagle_chart_domain = self.eagle_convert_into_proper_domain(rec.eagle_domain, rec)
                eagle_chart_data['previous_domain'] = eagle_chart_domain
                orderby = rec.eagle_sort_by_field.name if rec.eagle_sort_by_field else "id"
                if rec.eagle_sort_by_order:
                    orderby = orderby + " " + rec.eagle_sort_by_order
                limit = rec.eagle_record_data_limit if rec.eagle_record_data_limit and rec.eagle_record_data_limit > 0 else False

                if ((rec.eagle_chart_data_count_type != "count" and eagle_chart_measure_field) or (
                        rec.eagle_chart_data_count_type == "count" and not eagle_chart_measure_field)) \
                        and not rec.eagle_chart_relation_sub_groupby:
                    if rec.eagle_chart_relation_groupby.ttype == 'date' and rec.eagle_chart_date_groupby in (
                            'minute', 'hour'):
                        raise ValidationError(_('Groupby field: {} cannot be aggregated by {}').format(
                            rec.eagle_chart_relation_groupby.display_name, rec.eagle_chart_date_groupby))
                        eagle_chart_date_groupby = 'day'
                    else:
                        eagle_chart_date_groupby = rec.eagle_chart_date_groupby

                    if (rec.eagle_chart_groupby_type == 'date_type' and rec.eagle_chart_date_groupby) or\
                            rec.eagle_chart_groupby_type != 'date_type':
                        eagle_chart_data = rec.eagle_fetch_chart_data(rec.eagle_model_name, eagle_chart_domain,
                                                                eagle_chart_measure_field,
                                                                eagle_chart_measure_field_2,
                                                                eagle_chart_groupby_relation_field,
                                                                eagle_chart_date_groupby,
                                                                rec.eagle_chart_groupby_type, orderby, limit,
                                                                rec.eagle_chart_data_count_type,
                                                                eagle_chart_measure_field_ids,
                                                                eagle_chart_measure_field_2_ids,
                                                                rec.eagle_chart_relation_groupby.id, eagle_chart_data)

                        if rec.eagle_chart_groupby_type == 'date_type' and rec.eagle_goal_enable and rec.eagle_dashboard_item_type in [
                            'eagle_bar_chart', 'eagle_horizontalBar_chart', 'eagle_line_chart',
                            'eagle_area_chart'] and rec.eagle_chart_groupby_type == "date_type":

                            if rec._context.get('current_id', False):
                                eagle_item_id = rec._context['current_id']
                            else:
                                eagle_item_id = rec.id

                            if rec.eagle_date_filter_selection == "l_none":
                                selected_start_date = rec._context.get('ksDateFilterStartDate', False)
                                selected_end_date = rec._context.get('ksDateFilterEndDate', False)

                            else:
                                if rec.eagle_date_filter_selection == "l_custom":
                                    selected_start_date  = rec.eagle_item_start_date
                                    selected_end_date = rec.eagle_item_start_date
                                else:
                                    eagle_date_data = eagle_get_date(rec.eagle_date_filter_selection)
                                    selected_start_date = eagle_date_data["selected_start_date"]
                                    selected_end_date = eagle_date_data["selected_end_date"]

                            if selected_start_date and selected_end_date:
                                selected_start_date = selected_start_date.strftime('%Y-%m-%d')
                                selected_end_date = selected_end_date.strftime('%Y-%m-%d')
                            eagle_goal_domain = [('eagle_dashboard_item', '=', eagle_item_id)]

                            if selected_start_date and selected_end_date:
                                eagle_goal_domain.extend([('eagle_goal_date', '>=', selected_start_date.split(" ")[0]),
                                                       ('eagle_goal_date', '<=', selected_end_date.split(" ")[0])])

                            eagle_date_data = rec.eagle_get_start_end_date(rec.eagle_model_name, eagle_chart_groupby_relation_field,
                                                                     rec.eagle_chart_relation_groupby.ttype,
                                                                     eagle_chart_domain,
                                                                     eagle_goal_domain)

                            labels = []
                            if eagle_date_data['start_date'] and eagle_date_data['end_date'] and rec.eagle_goal_lines:
                                labels = self.generate_timeserise(eagle_date_data['start_date'], eagle_date_data['end_date'],
                                                                  rec.eagle_chart_date_groupby)

                            eagle_goal_records = self.env['eagle_dashboard.item_goal'].read_group(
                                eagle_goal_domain, ['eagle_goal_value'],
                                ['eagle_goal_date' + ":" + eagle_chart_date_groupby])
                            eagle_goal_labels = []
                            eagle_goal_dataset = []
                            goal_dataset = []

                            if rec.eagle_goal_lines and len(rec.eagle_goal_lines) != 0:
                                eagle_goal_domains = {}
                                for res in eagle_goal_records:
                                    if res['eagle_goal_date' + ":" + eagle_chart_date_groupby]:
                                        eagle_goal_labels.append(res['eagle_goal_date' + ":" + eagle_chart_date_groupby])
                                        eagle_goal_dataset.append(res['eagle_goal_value'])
                                        eagle_goal_domains[res['eagle_goal_date' + ":" + eagle_chart_date_groupby]] = res['__domain']

                                for goal_domain in eagle_goal_domains.keys():
                                    eagle_goal_doamins = []
                                    for item in eagle_goal_domains[goal_domain]:

                                        if 'eagle_goal_date' in item:
                                            domain = list(item)
                                            domain[0] = eagle_chart_groupby_relation_field
                                            domain = tuple(domain)
                                            eagle_goal_doamins.append(domain)
                                    eagle_goal_doamins.insert(0, '&')
                                    eagle_goal_domains[goal_domain] = eagle_goal_doamins

                                domains = {}
                                counter = 0
                                for label in eagle_chart_data['labels']:
                                    domains[label] = eagle_chart_data['domains'][counter]
                                    counter += 1

                                eagle_chart_records_dates = eagle_chart_data['labels'] + list(
                                    set(eagle_goal_labels) - set(eagle_chart_data['labels']))

                                eagle_chart_records = []
                                for label in labels:
                                    if label in eagle_chart_records_dates:
                                        eagle_chart_records.append(label)

                                eagle_chart_data['domains'].clear()
                                datasets = []
                                for dataset in eagle_chart_data['datasets']:
                                    datasets.append(dataset['data'].copy())

                                for dataset in eagle_chart_data['datasets']:
                                    dataset['data'].clear()

                                for label in eagle_chart_records:
                                    domain = domains.get(label, False)
                                    if domain:
                                        eagle_chart_data['domains'].append(domain)
                                    else:
                                        eagle_chart_data['domains'].append(eagle_goal_domains.get(label, []))
                                    counterr = 0
                                    if label in eagle_chart_data['labels']:
                                        index = eagle_chart_data['labels'].index(label)

                                        for dataset in eagle_chart_data['datasets']:
                                            dataset['data'].append(datasets[counterr][index])
                                            counterr += 1

                                    else:
                                        for dataset in eagle_chart_data['datasets']:
                                            dataset['data'].append(0.00)

                                    if label in eagle_goal_labels:
                                        index = eagle_goal_labels.index(label)
                                        goal_dataset.append(eagle_goal_dataset[index])
                                    else:
                                        goal_dataset.append(0.00)

                                eagle_chart_data['labels'] = eagle_chart_records
                            else:
                                if rec.eagle_standard_goal_value:
                                    length = len(eagle_chart_data['datasets'][0]['data'])
                                    for i in range(length):
                                        goal_dataset.append(rec.eagle_standard_goal_value)
                            eagle_goal_datasets = {
                                'label': 'Target',
                                'data': goal_dataset,
                            }
                            if rec.eagle_goal_bar_line:
                                eagle_goal_datasets['type'] = 'line'
                                eagle_chart_data['datasets'].insert(0, eagle_goal_datasets)
                            else:
                                eagle_chart_data['datasets'].append(eagle_goal_datasets)

                elif rec.eagle_chart_relation_sub_groupby and ((rec.eagle_chart_sub_groupby_type == 'relational_type') or
                                                            (rec.eagle_chart_sub_groupby_type == 'selection') or
                                                            (rec.eagle_chart_sub_groupby_type == 'date_type' and
                                                             rec.eagle_chart_date_sub_groupby) or
                                                            (rec.eagle_chart_sub_groupby_type == 'other')):
                    if rec.eagle_chart_relation_sub_groupby.ttype == 'date':
                        if rec.eagle_chart_date_sub_groupby in ('minute', 'hour'):
                            raise ValidationError(_('Sub Groupby field: {} cannot be aggregated by {}').format(
                                rec.eagle_chart_relation_sub_groupby.display_name, rec.eagle_chart_date_sub_groupby))
                        if rec.eagle_chart_date_groupby in ('minute', 'hour'):
                            raise ValidationError(_('Groupby field: {} cannot be aggregated by {}').format(
                                rec.eagle_chart_relation_sub_groupby.display_name, rec.eagle_chart_date_groupby))
                        # doesn't have time in date
                        eagle_chart_date_sub_groupby = rec.eagle_chart_date_sub_groupby
                        eagle_chart_date_groupby = rec.eagle_chart_date_groupby
                    else:
                        eagle_chart_date_sub_groupby = rec.eagle_chart_date_sub_groupby
                        eagle_chart_date_groupby = rec.eagle_chart_date_groupby
                    if len(eagle_chart_measure_field) != 0 or rec.eagle_chart_data_count_type == 'count':
                        if rec.eagle_chart_groupby_type == 'date_type' and eagle_chart_date_groupby:
                            eagle_chart_group = rec.eagle_chart_relation_groupby.name + ":" + eagle_chart_date_groupby
                        else:
                            eagle_chart_group = rec.eagle_chart_relation_groupby.name

                        if rec.eagle_chart_sub_groupby_type == 'date_type' and rec.eagle_chart_date_sub_groupby:
                            eagle_chart_sub_groupby_field = rec.eagle_chart_relation_sub_groupby.name + ":" + \
                                                         eagle_chart_date_sub_groupby
                        else:
                            eagle_chart_sub_groupby_field = rec.eagle_chart_relation_sub_groupby.name

                        eagle_chart_groupby_relation_fields = [eagle_chart_group, eagle_chart_sub_groupby_field]
                        eagle_chart_record = self.env[rec.eagle_model_name].read_group(eagle_chart_domain,
                                                                                 set(eagle_chart_measure_field +
                                                                                     eagle_chart_measure_field_2 +
                                                                                     [eagle_chart_groupby_relation_field,
                                                                              rec.eagle_chart_relation_sub_groupby.name]),
                                                                                 eagle_chart_groupby_relation_fields,
                                                                                 orderby=orderby, limit=limit,
                                                                                 lazy=False)
                        chart_data = []
                        chart_sub_data = []
                        for res in eagle_chart_record:
                            domain = res.get('__domain', [])
                            if res[eagle_chart_groupby_relation_fields[0]] is not False:
                                if rec.eagle_chart_groupby_type == 'date_type':
                                    # x-axis modification
                                    if rec.eagle_chart_date_groupby == "day" \
                                            and rec.eagle_chart_date_sub_groupby in ["quarter", "year"]:
                                        label = " ".join(res[eagle_chart_groupby_relation_fields[0]].split(" ")[0:2])
                                    elif rec.eagle_chart_date_groupby in ["minute", "hour"] and \
                                            rec.eagle_chart_date_sub_groupby in ["month", "week", "quarter", "year"]:
                                        label = " ".join(res[eagle_chart_groupby_relation_fields[0]].split(" ")[0:3])
                                    else:
                                        label = res[eagle_chart_groupby_relation_fields[0]].split(" ")[0]
                                elif rec.eagle_chart_groupby_type == 'selection':
                                    selection = res[eagle_chart_groupby_relation_fields[0]]
                                    label = dict(self.env[rec.eagle_model_name].fields_get(
                                        allfields=[eagle_chart_groupby_relation_fields[0]])
                                                 [eagle_chart_groupby_relation_fields[0]]['selection'])[selection]
                                elif rec.eagle_chart_groupby_type == 'relational_type':
                                    label = res[eagle_chart_groupby_relation_fields[0]][1]._value
                                elif rec.eagle_chart_groupby_type == 'other':
                                    label = res[eagle_chart_groupby_relation_fields[0]]

                                labels = []
                                value = []
                                value_2 = []
                                labels_2 = []
                                if rec.eagle_chart_data_count_type != 'count':
                                    for ress in rec.eagle_chart_measure_field:
                                        if rec.eagle_chart_sub_groupby_type == 'date_type':
                                            if res[eagle_chart_groupby_relation_fields[1]] is not False:
                                                labels.append(res[eagle_chart_groupby_relation_fields[1]].split(" ")[
                                                                      0] + " " + ress.field_description)
                                            else:
                                                labels.append(str(res[eagle_chart_groupby_relation_fields[1]]) + " " +
                                                              ress.field_description)
                                        elif rec.eagle_chart_sub_groupby_type == 'selection':
                                            if res[eagle_chart_groupby_relation_fields[1]] is not False:
                                                selection = res[eagle_chart_groupby_relation_fields[1]]
                                                labels.append(dict(self.env[rec.eagle_model_name].fields_get(
                                                    allfields=[eagle_chart_groupby_relation_fields[1]])
                                                                   [eagle_chart_groupby_relation_fields[1]]['selection'])[
                                                                  selection]
                                                              + " " + ress.field_description)
                                            else:
                                                labels.append(str(res[eagle_chart_groupby_relation_fields[1]]))
                                        elif rec.eagle_chart_sub_groupby_type == 'relational_type':
                                            if res[eagle_chart_groupby_relation_fields[1]] is not False:
                                                labels.append(res[eagle_chart_groupby_relation_fields[1]][1]._value
                                                              + " " + ress.field_description)
                                            else:
                                                labels.append(str(res[eagle_chart_groupby_relation_fields[1]])
                                                              + " " +ress.field_description)
                                        elif rec.eagle_chart_sub_groupby_type == 'other':
                                            if res[eagle_chart_groupby_relation_fields[1]] is not False:
                                                labels.append(str(res[eagle_chart_groupby_relation_fields[1]])
                                                          + "\'s " + ress.field_description)
                                            else:
                                                labels.append(str(res[eagle_chart_groupby_relation_fields[1]])
                                                              + " " +ress.field_description)

                                        value.append(res.get(
                                            ress.name,0) if rec.eagle_chart_data_count_type == 'sum' else res.get(
                                            ress.name,0) / res.get('__count'))

                                    if rec.eagle_chart_measure_field_2 and rec.eagle_dashboard_item_type == 'eagle_bar_chart':
                                        for ress in rec.eagle_chart_measure_field_2:
                                            if rec.eagle_chart_sub_groupby_type == 'date_type':
                                                if res[eagle_chart_groupby_relation_fields[1]] is not False:
                                                    labels_2.append(
                                                        res[eagle_chart_groupby_relation_fields[1]].split(" ")[0] + " "
                                                        + ress.field_description)
                                                else:
                                                    labels_2.append(str(res[eagle_chart_groupby_relation_fields[1]]) +
                                                                    " " + ress.field_description)
                                            elif rec.eagle_chart_sub_groupby_type == 'selection':
                                                selection = res[eagle_chart_groupby_relation_fields[1]]
                                                labels_2.append(dict(self.env[rec.eagle_model_name].fields_get(
                                                    allfields=[eagle_chart_groupby_relation_fields[1]])
                                                                     [eagle_chart_groupby_relation_fields[1]][
                                                                         'selection'])[
                                                                    selection] + " " + ress.field_description)
                                            elif rec.eagle_chart_sub_groupby_type == 'relational_type':
                                                if res[eagle_chart_groupby_relation_fields[1]] is not False:
                                                    labels_2.append(
                                                        res[eagle_chart_groupby_relation_fields[1]][1]._value + " " +
                                                        ress.field_description)
                                                else:
                                                    labels_2.append(res[eagle_chart_groupby_relation_fields[1]] +
                                                                     " " + ress.field_description)
                                            elif rec.eagle_chart_sub_groupby_type == 'other':
                                                labels_2.append(str(
                                                    res[eagle_chart_groupby_relation_fields[1]]) + " " +
                                                                ress.field_description)

                                            value_2.append(res.get(
                                                ress.name,0) if rec.eagle_chart_data_count_type == 'sum' else res.get(
                                                ress.name,0) / res.get('__count'))

                                        chart_sub_data.append({
                                            'value': value_2,
                                            'labels': label,
                                            'series': labels_2,
                                            'domain': domain,
                                        })
                                else:
                                    if rec.eagle_chart_sub_groupby_type == 'date_type':
                                        if res[eagle_chart_groupby_relation_fields[1]] is not False:
                                            labels.append(res[eagle_chart_groupby_relation_fields[1]].split(" ")[0])
                                        else:
                                            labels.append(str(res[eagle_chart_groupby_relation_fields[1]]))
                                    elif rec.eagle_chart_sub_groupby_type == 'selection':
                                        selection = res[eagle_chart_groupby_relation_fields[1]]
                                        labels.append(dict(self.env[rec.eagle_model_name].fields_get(
                                            allfields=[eagle_chart_groupby_relation_fields[1]])
                                                           [eagle_chart_groupby_relation_fields[1]]['selection'])[
                                                          selection])
                                    elif rec.eagle_chart_sub_groupby_type == 'relational_type':
                                        if res[eagle_chart_groupby_relation_fields[1]] is not False:
                                            labels.append(res[eagle_chart_groupby_relation_fields[1]][1]._value)
                                        else:
                                            labels.append(str(res[eagle_chart_groupby_relation_fields[1]]))
                                    elif rec.eagle_chart_sub_groupby_type == 'other':
                                        labels.append(res[eagle_chart_groupby_relation_fields[1]])
                                    value.append(res['__count'])

                                chart_data.append({
                                    'value': value,
                                    'labels': label,
                                    'series': labels,
                                    'domain': domain,
                                })

                        xlabels = []
                        series = []
                        values = {}
                        domains = {}
                        for data in chart_data:
                            label = data['labels']
                            serie = data['series']
                            domain = data['domain']

                            if (len(xlabels) == 0) or (label not in xlabels):
                                xlabels.append(label)

                            if (label not in domains):
                                domains[label] = domain
                            else:
                                domains[label].insert(0, '|')
                                domains[label] = domains[label] + domain

                            series = series + serie
                            value = data['value']
                            counter = 0
                            for seri in serie:
                                if seri not in values:
                                    values[seri] = {}
                                if label in values[seri]:
                                    values[seri][label] = values[seri][label] + value[counter]
                                else:
                                    values[seri][label] = value[counter]
                                counter += 1

                        final_datasets = []
                        for serie in series:
                            if serie not in final_datasets:
                                final_datasets.append(serie)

                        eagle_data = []
                        for dataset in final_datasets:
                            eagle_dataset = {
                                'value': [],
                                'key': dataset
                            }
                            for label in xlabels:
                                eagle_dataset['value'].append({
                                    'domain': domains[label],
                                    'x': label,
                                    'y': values[dataset][label] if label in values[dataset] else 0
                                })
                            eagle_data.append(eagle_dataset)

                        if rec.eagle_chart_relation_sub_groupby.name == rec.eagle_chart_relation_groupby.name == rec.eagle_sort_by_field.name:
                            eagle_data = rec.eagle_sort_sub_group_by_records(eagle_data, rec.eagle_chart_groupby_type,
                                                                       rec.eagle_chart_date_groupby, rec.eagle_sort_by_order,
                                                                       rec.eagle_chart_date_sub_groupby)

                        eagle_chart_data = {
                            'labels': [],
                            'datasets': [],
                            'domains': [],
                            'eagle_selection': "",
                            'eagle_currency': 0,
                            'eagle_field': "",
                            'previous_domain': eagle_chart_domain
                        }

                        if rec.eagle_unit and rec.eagle_unit_selection == 'monetary':
                            eagle_chart_data['eagle_selection'] += rec.eagle_unit_selection
                            eagle_chart_data['eagle_currency'] += rec.env.user.company_id.currency_id.id
                        elif rec.eagle_unit and rec.eagle_unit_selection == 'custom':
                            eagle_chart_data['eagle_selection'] += rec.eagle_unit_selection
                            if rec.eagle_chart_unit:
                                eagle_chart_data['eagle_field'] += rec.eagle_chart_unit

                        if len(eagle_data) != 0:
                            for res in eagle_data[0]['value']:
                                eagle_chart_data['labels'].append(res['x'])
                                eagle_chart_data['domains'].append(res['domain'])
                            if rec.eagle_chart_measure_field_2 and rec.eagle_dashboard_item_type == 'eagle_bar_chart':
                                eagle_chart_data['eagle_show_second_y_scale'] = True
                                values_2 = {}
                                series_2 = []
                                for data in chart_sub_data:
                                    label = data['labels']
                                    serie = data['series']
                                    series_2 = series_2 + serie
                                    value = data['value']

                                    counter = 0
                                    for seri in serie:
                                        if seri not in values_2:
                                            values_2[seri] = {}
                                        if label in values_2[seri]:
                                            values_2[seri][label] = values_2[seri][label] + value[counter]
                                        else:
                                            values_2[seri][label] = value[counter]
                                        counter += 1
                                final_datasets_2 = []
                                for serie in series_2:
                                    if serie not in final_datasets_2:
                                        final_datasets_2.append(serie)
                                eagle_data_2 = []
                                for dataset in final_datasets_2:
                                    eagle_dataset = {
                                        'value': [],
                                        'key': dataset
                                    }
                                    for label in xlabels:
                                        eagle_dataset['value'].append({
                                            'x': label,
                                            'y': values_2[dataset][label] if label in values_2[dataset] else 0
                                        })
                                    eagle_data_2.append(eagle_dataset)

                                for eagle_dat in eagle_data_2:
                                    dataset = {
                                        'label': eagle_dat['key'],
                                        'data': [],
                                        'type': 'line',
                                        'yAxisID': 'y-axis-1'

                                    }
                                    for res in eagle_dat['value']:
                                        dataset['data'].append(res['y'])

                                    eagle_chart_data['datasets'].append(dataset)
                            for eagle_dat in eagle_data:
                                dataset = {
                                    'label': eagle_dat['key'],
                                    'data': []
                                }
                                for res in eagle_dat['value']:
                                    dataset['data'].append(res['y'])

                                eagle_chart_data['datasets'].append(dataset)

                            if rec.eagle_goal_enable and rec.eagle_standard_goal_value and rec.eagle_dashboard_item_type in [
                                'eagle_bar_chart', 'eagle_line_chart', 'eagle_area_chart', 'eagle_horizontalBar_chart']:
                                goal_dataset = []
                                length = len(eagle_chart_data['datasets'][0]['data'])
                                for i in range(length):
                                    goal_dataset.append(rec.eagle_standard_goal_value)
                                eagle_goal_datasets = {
                                    'label': 'Target',
                                    'data': goal_dataset,
                                }
                                if rec.eagle_goal_bar_line and rec.eagle_dashboard_item_type != 'eagle_horizontalBar_chart':
                                    eagle_goal_datasets['type'] = 'line'
                                    eagle_chart_data['datasets'].insert(0, eagle_goal_datasets)
                                else:
                                    eagle_chart_data['datasets'].append(eagle_goal_datasets)
                    else:
                        eagle_chart_data = False

                rec.eagle_chart_data = json.dumps(eagle_chart_data)
            elif not rec.eagle_dashboard_item_type or rec.eagle_dashboard_item_type == 'eagle_tile':
                rec.eagle_chart_measure_field = False
                rec.eagle_chart_measure_field_2 = False
                rec.eagle_chart_relation_groupby = False


    @api.multi
    @api.depends('eagle_domain', 'eagle_dashboard_item_type', 'eagle_model_id', 'eagle_sort_by_field', 'eagle_sort_by_order',
                 'eagle_record_data_limit', 'eagle_list_view_fields', 'eagle_list_view_type', 'eagle_list_view_group_fields',
                 'eagle_chart_groupby_type', 'eagle_chart_date_groupby', 'eagle_date_filter_field', 'eagle_item_end_date',
                 'eagle_item_start_date', 'eagle_compare_period', 'eagle_year_period', 'eagle_list_target_deviation_field',
                 'eagle_goal_enable', 'eagle_standard_goal_value', 'eagle_goal_lines')
    def eagle_get_list_view_data(self):
        for rec in self:
            if rec.eagle_list_view_type and rec.eagle_dashboard_item_type and rec.eagle_dashboard_item_type == 'eagle_list_view' and \
                    rec.eagle_model_id:
                eagle_list_view_data = {'label': [],
                                     'data_rows': [], 'model': rec.eagle_model_name}

                eagle_chart_domain = self.eagle_convert_into_proper_domain(rec.eagle_domain, rec)
                orderby = rec.eagle_sort_by_field.name if rec.eagle_sort_by_field else "id"
                if rec.eagle_sort_by_order:
                    orderby = orderby + " " + rec.eagle_sort_by_order
                limit = rec.eagle_record_data_limit if rec.eagle_record_data_limit and rec.eagle_record_data_limit > 0 else False

                if rec.eagle_list_view_type == "ungrouped":
                    if rec.eagle_list_view_fields:
                        eagle_list_view_data = rec.eagle_fetch_list_view_data(rec)

                elif rec.eagle_list_view_type == "grouped" and rec.eagle_list_view_group_fields and rec.eagle_chart_relation_groupby:
                    eagle_list_fields = []

                    if rec.eagle_chart_groupby_type == 'relational_type':
                        eagle_list_view_data['list_view_type'] = 'relational_type'
                        eagle_list_view_data['groupby'] = rec.eagle_chart_relation_groupby.name
                        eagle_list_fields.append(rec.eagle_chart_relation_groupby.name)
                        eagle_list_view_data['label'].append(rec.eagle_chart_relation_groupby.field_description)
                        for res in rec.eagle_list_view_group_fields:
                            eagle_list_fields.append(res.name)
                            eagle_list_view_data['label'].append(res.field_description)

                        eagle_list_view_records = self.env[rec.eagle_model_name].read_group(eagle_chart_domain, eagle_list_fields,
                                                                                      [rec.eagle_chart_relation_groupby.name],
                                                                                      orderby=orderby, limit=limit)
                        for res in eagle_list_view_records:
                            if all(list_fields in res for list_fields in eagle_list_fields) and res[
                                rec.eagle_chart_relation_groupby.name]:
                                counter = 0
                                data_row = {'id': res[rec.eagle_chart_relation_groupby.name][0], 'data': [],
                                            'domain': json.dumps(res['__domain'])}
                                for field_rec in eagle_list_fields:
                                    if counter == 0:
                                        data_row['data'].append(res[field_rec][1]._value)
                                    else:
                                        data_row['data'].append(res[field_rec])
                                    counter += 1
                                eagle_list_view_data['data_rows'].append(data_row)

                    elif rec.eagle_chart_groupby_type == 'date_type' and rec.eagle_chart_date_groupby:
                        eagle_list_view_data['list_view_type'] = 'date_type'
                        eagle_list_field = []
                        eagle_list_view_data[
                            'groupby'] = rec.eagle_chart_relation_groupby.name + ':' + rec.eagle_chart_date_groupby
                        eagle_list_field.append(rec.eagle_chart_relation_groupby.name)
                        eagle_list_fields.append(rec.eagle_chart_relation_groupby.name + ':' + rec.eagle_chart_date_groupby)
                        eagle_list_view_data['label'].append(
                            rec.eagle_chart_relation_groupby.field_description + ' : ' + rec.eagle_chart_date_groupby.capitalize())
                        for res in rec.eagle_list_view_group_fields:
                            eagle_list_fields.append(res.name)
                            eagle_list_field.append(res.name)
                            eagle_list_view_data['label'].append(res.field_description)

                        list_target_deviation_field = []
                        if rec.eagle_goal_enable and rec.eagle_list_target_deviation_field:
                            list_target_deviation_field.append(rec.eagle_list_target_deviation_field.name)
                            if rec.eagle_list_target_deviation_field.name in eagle_list_field:
                                eagle_list_field.remove(rec.eagle_list_target_deviation_field.name)
                                eagle_list_fields.remove(rec.eagle_list_target_deviation_field.name)
                                eagle_list_view_data['label'].remove(rec.eagle_list_target_deviation_field.field_description)

                        eagle_list_view_records = self.env[rec.eagle_model_name].read_group(eagle_chart_domain,
                                                                                      eagle_list_field
                                                                                      + list_target_deviation_field,
                                                                              [rec.eagle_chart_relation_groupby.name + ':'
                                                                               + rec.eagle_chart_date_groupby],
                                                                                      orderby=orderby, limit=limit)
                        if all(list_fields in res for res in eagle_list_view_records for list_fields in
                               eagle_list_fields + list_target_deviation_field):
                            for res in eagle_list_view_records:
                                counter = 0
                                data_row = {'id': 0, 'data': [], 'domain': json.dumps(res['__domain'])}
                                for field_rec in eagle_list_fields:
                                    data_row['data'].append(res[field_rec])
                                eagle_list_view_data['data_rows'].append(data_row)

                            if rec.eagle_goal_enable:
                                eagle_list_labels = []
                                eagle_list_view_data['label'].append("Target")

                                if rec.eagle_list_target_deviation_field:
                                    eagle_list_view_data['label'].append(rec.eagle_list_target_deviation_field.field_description)
                                    eagle_list_view_data['label'].append("Achievement")
                                    eagle_list_view_data['label'].append("Deviation")

                                for res in eagle_list_view_records:
                                    eagle_list_labels.append(res[eagle_list_view_data['groupby']])
                                eagle_list_view_data2 = rec.get_target_list_view_data(eagle_list_view_records, rec,
                                                                                   eagle_list_fields,
                                                                                   eagle_list_view_data['groupby'],
                                                                                   list_target_deviation_field,
                                                                                   eagle_chart_domain)
                                eagle_list_view_data['data_rows'] = eagle_list_view_data2['data_rows']

                    elif rec.eagle_chart_groupby_type == 'selection':
                        eagle_list_view_data['list_view_type'] = 'selection'
                        eagle_list_view_data['groupby'] = rec.eagle_chart_relation_groupby.name
                        eagle_selection_field = rec.eagle_chart_relation_groupby.name
                        eagle_list_view_data['label'].append(rec.eagle_chart_relation_groupby.field_description)
                        for res in rec.eagle_list_view_group_fields:
                            eagle_list_fields.append(res.name)
                            eagle_list_view_data['label'].append(res.field_description)

                        eagle_list_view_records = self.env[rec.eagle_model_name].read_group(eagle_chart_domain, eagle_list_fields,
                                                                                      [
                                                                                          rec.eagle_chart_relation_groupby.name],
                                                                                      orderby=orderby, limit=limit)
                        for res in eagle_list_view_records:
                            if all(list_fields in res for list_fields in eagle_list_fields):
                                counter = 0
                                data_row = {'id': 0, 'data': [], 'domain': json.dumps(res['__domain'])}
                                if res[eagle_selection_field]:
                                    data_row['data'].append(dict(
                                    self.env[rec.eagle_model_name].fields_get(allfields=eagle_selection_field)
                                    [eagle_selection_field]['selection'])[res[eagle_selection_field]])
                                else:
                                    data_row['data'].append(" ")
                                for field_rec in eagle_list_fields:
                                    data_row['data'].append(res[field_rec])
                                eagle_list_view_data['data_rows'].append(data_row)

                    elif rec.eagle_chart_groupby_type == 'other':
                        eagle_list_view_data['list_view_type'] = 'other'
                        eagle_list_view_data['groupby'] = rec.eagle_chart_relation_groupby.name
                        eagle_list_fields.append(rec.eagle_chart_relation_groupby.name)
                        eagle_list_view_data['label'].append(rec.eagle_chart_relation_groupby.field_description)
                        for res in rec.eagle_list_view_group_fields:
                            eagle_list_fields.append(res.name)
                            eagle_list_view_data['label'].append(res.field_description)

                        eagle_list_view_records = self.env[rec.eagle_model_name].read_group(eagle_chart_domain, eagle_list_fields,
                                                                                      [
                                                                                          rec.eagle_chart_relation_groupby.name],
                                                                                      orderby=orderby, limit=limit)
                        for res in eagle_list_view_records:
                            if all(list_fields in res for list_fields in eagle_list_fields):
                                counter = 0
                                data_row = {'id': 0, 'data': [],'domain': json.dumps(res['__domain'])}

                                for field_rec in eagle_list_fields:
                                    if counter == 0:
                                        data_row['data'].append(res[field_rec])
                                    else:
                                        if rec.eagle_chart_relation_groupby.name == field_rec:
                                            data_row['data'].append(res[field_rec] * res[field_rec + '_count'])
                                        else:
                                            data_row['data'].append(res[field_rec])
                                    counter += 1
                                eagle_list_view_data['data_rows'].append(data_row)

                rec.eagle_list_view_data = json.dumps(eagle_list_view_data)
            else:
                rec.eagle_list_view_data = False

    def get_target_list_view_data(self, eagle_list_view_records, rec, eagle_list_fields, eagle_group_by,
                                  target_deviation_field, eagle_chart_domain):
        eagle_list_view_data = {}
        eagle_list_labels = []
        eagle_list_records = {}
        eagle_domains = {}
        for res in eagle_list_view_records:
            eagle_list_labels.append(res[eagle_group_by])
            eagle_domains[res[eagle_group_by]] = res['__domain']
            eagle_list_records[res[eagle_group_by]] = {'measure_field': [], 'deviation_value': 0.0}
            eagle_list_records[res[eagle_group_by]]['measure_field'] = []
            for fields in eagle_list_fields[1:]:
                eagle_list_records[res[eagle_group_by]]['measure_field'].append(res[fields])
            for field in target_deviation_field:
                eagle_list_records[res[eagle_group_by]]['deviation'] = res[field]

        if rec._context.get('current_id', False):
            eagle_item_id = rec._context['current_id']
        else:
            eagle_item_id = rec.id

        if rec.eagle_date_filter_selection_2 == "l_none":
            selected_start_date = rec._context.get('ksDateFilterStartDate', False)
            selected_end_date = rec._context.get('ksDateFilterEndDate', False)
        else:
            selected_start_date = rec.eagle_item_start_date
            selected_end_date = rec.eagle_item_end_date

        eagle_goal_domain = [('eagle_dashboard_item', '=', eagle_item_id)]

        if selected_start_date and selected_end_date:
            eagle_goal_domain.extend([('eagle_goal_date', '>=', selected_start_date.strftime("%Y-%m-%d")),
                                   ('eagle_goal_date', '<=', selected_end_date.strftime("%Y-%m-%d"))])

        eagle_date_data = rec.eagle_get_start_end_date(rec.eagle_model_name, rec.eagle_chart_relation_groupby.name,
                                                 rec.eagle_chart_relation_groupby.ttype,
                                                 eagle_chart_domain,
                                                 eagle_goal_domain)

        labels = []
        if eagle_date_data['start_date'] and eagle_date_data['end_date'] and rec.eagle_goal_lines:
            labels = self.generate_timeserise(eagle_date_data['start_date'], eagle_date_data['end_date'],
                                              rec.eagle_chart_date_groupby)
        eagle_goal_records = self.env['eagle_dashboard.item_goal'].read_group(
            eagle_goal_domain, ['eagle_goal_value'],
            ['eagle_goal_date' + ":" + rec.eagle_chart_date_groupby], )

        eagle_goal_labels = []
        eagle_goal_dataset = {}
        eagle_list_view_data['data_rows'] = []
        if rec.eagle_goal_lines and len(rec.eagle_goal_lines) != 0:
            eagle_goal_domains = {}
            for res in eagle_goal_records:
                if res['eagle_goal_date' + ":" + rec.eagle_chart_date_groupby]:
                    eagle_goal_labels.append(res['eagle_goal_date' + ":" + rec.eagle_chart_date_groupby])
                    eagle_goal_dataset[res['eagle_goal_date' + ":" + rec.eagle_chart_date_groupby]] = res['eagle_goal_value']
                    eagle_goal_domains[res['eagle_goal_date' + ":" + rec.eagle_chart_date_groupby]] = res['__domain']

            for goal_domain in eagle_goal_domains.keys():
                eagle_goal_doamins = []
                for item in eagle_goal_domains[goal_domain]:

                    if 'eagle_goal_date' in item:
                        domain = list(item)
                        domain[0] = eagle_group_by.split(":")[0]
                        domain = tuple(domain)
                        eagle_goal_doamins.append(domain)
                eagle_goal_doamins.insert(0, '&')
                eagle_goal_domains[goal_domain] = eagle_goal_doamins

            eagle_chart_records_dates = eagle_list_labels + list(
                set(eagle_goal_labels) - set(eagle_list_labels))

            eagle_list_labels_dates = []
            for label in labels:
                if label in eagle_chart_records_dates:
                    eagle_list_labels_dates.append(label)

            for label in eagle_list_labels_dates:
                data_rows = {'data': [label]}
                data = eagle_list_records.get(label, False)
                if data:
                    data_rows['data'] = data_rows['data'] + data['measure_field']
                    data_rows['domain'] = json.dumps(eagle_domains[label])
                else:
                    for fields in eagle_list_fields[1:]:
                        data_rows['data'].append(0.0)
                    data_rows['domain'] = json.dumps(eagle_goal_domains[label])

                target_value = (eagle_goal_dataset.get(label, 0.0))
                data_rows['data'].append(target_value)

                for field in target_deviation_field:
                    if data:
                        data_rows['data'].append(data['deviation'])
                        value = data['deviation']
                    else:
                        data_rows['data'].append(0.0)
                        value = 0
                    if target_value:
                        acheivement = round(((value) / target_value) * 100)
                        acheivement = str(acheivement) + "%"
                    else:
                        acheivement = ""
                    deviation = (value - target_value)

                    data_rows['data'].append(acheivement)
                    data_rows['data'].append(deviation)

                eagle_list_view_data['data_rows'].append(data_rows)

        else:
            for res in eagle_list_view_records:
                if all(list_fields in res for list_fields in eagle_list_fields):
                    counter = 0
                    data_row = {'id': 0, 'data': [],}
                    for field_rec in eagle_list_fields:
                        data_row['data'].append(res[field_rec])
                    data_row['data'].append(rec.eagle_standard_goal_value)
                    data_row['domain'] = json.dumps(res['__domain'])
                    for field in target_deviation_field:
                        value = res[field]
                        data_row['data'].append(res[field])
                        target_value = rec.eagle_standard_goal_value

                        if target_value:
                            acheivement = round(((value) / target_value) * 100)
                            acheivement = str(acheivement) + "%"
                        else:
                            acheivement = ""

                        deviation = (value - target_value)
                        data_row['data'].append(acheivement)
                        data_row['data'].append(deviation)
                    eagle_list_view_data['data_rows'].append(data_row)

        return eagle_list_view_data

    @api.model
    def eagle_fetch_list_view_data(self, rec,  limit=15, offset=0):
        eagle_list_view_data = {'label': [],
                             'data_rows': [], 'model': rec.eagle_model_name}

        eagle_chart_domain = rec.eagle_convert_into_proper_domain(rec.eagle_domain, rec)
        orderby = rec.eagle_sort_by_field.name if rec.eagle_sort_by_field else "id"
        if rec.eagle_sort_by_order:
            orderby = orderby + " " + rec.eagle_sort_by_order
        eagle_limit = rec.eagle_record_data_limit if rec.eagle_record_data_limit and rec.eagle_record_data_limit > 0 else False

        if eagle_limit:
            eagle_limit = eagle_limit - offset
            if eagle_limit  < 15:
                limit = eagle_limit
            else:
                limit = 15
        if rec.eagle_list_view_fields:
            eagle_list_view_data['list_view_type'] = 'other'
            eagle_list_view_data['groupby'] = False
            eagle_list_view_data['label'] = []
            eagle_list_view_data['date_index'] = []
            for res in rec.eagle_list_view_fields:
                if (res.ttype == "datetime" or res.ttype == "date"):
                    index = len(eagle_list_view_data['label'])
                    eagle_list_view_data['label'].append(res.field_description)
                    eagle_list_view_data['date_index'].append(index)
                else:
                    eagle_list_view_data['label'].append(res.field_description)

            eagle_list_view_fields = [res.name for res in rec.eagle_list_view_fields]
            eagle_list_view_field_type = [res.ttype for res in rec.eagle_list_view_fields]
        try:
            eagle_list_view_records = self.env[rec.eagle_model_name].search_read(eagle_chart_domain,
                                                                       eagle_list_view_fields,
                                                                       order=orderby, limit=limit, offset=offset)
        except Exception as e:
            eagle_list_view_data = False
            return eagle_list_view_data
        for res in eagle_list_view_records:
            counter = 0
            data_row = {'id': res['id'], 'data': []}
            for field_rec in eagle_list_view_fields:
                if type(res[field_rec]) == fields.datetime or type(res[field_rec]) == fields.date:
                    res[field_rec] = res[field_rec].strftime("%D %T")
                elif eagle_list_view_field_type[counter] == "many2one":
                    if res[field_rec]:
                        res[field_rec] = res[field_rec][1]
                data_row['data'].append(res[field_rec])
                counter += 1
            eagle_list_view_data['data_rows'].append(data_row)

        return eagle_list_view_data

    @api.onchange('eagle_dashboard_item_type')
    def set_color_palette(self):
        for rec in self:
            if rec.eagle_dashboard_item_type == "eagle_bar_chart" or rec.eagle_dashboard_item_type == "eagle_horizontalBar_chart" or rec.eagle_dashboard_item_type == "eagle_line_chart" or rec.eagle_dashboard_item_type == "eagle_area_chart":
                rec.eagle_chart_item_color = "cool"
            else:
                rec.eagle_chart_item_color = "default"

    #  Time Filter Calculation
    @api.multi
    @api.onchange('eagle_date_filter_selection')
    def eagle_set_date_filter(self):
        for rec in self:
            if (not rec.eagle_date_filter_selection) or rec.eagle_date_filter_selection == "l_none":
                rec.eagle_item_start_date = rec.eagle_item_end_date = False
            elif rec.eagle_date_filter_selection != 'l_custom':
                eagle_date_data = eagle_get_date(rec.eagle_date_filter_selection)
                rec.eagle_item_start_date = eagle_date_data["selected_start_date"]
                rec.eagle_item_end_date = eagle_date_data["selected_end_date"]

    @api.multi
    @api.depends('eagle_dashboard_item_type', 'eagle_goal_enable', 'eagle_standard_goal_value', 'eagle_record_count',
                 'eagle_record_count_2', 'eagle_previous_period', 'eagle_compare_period', 'eagle_year_period',
                 'eagle_compare_period_2', 'eagle_year_period_2')
    def eagle_get_kpi_data(self):
        for rec in self:
            if rec.eagle_dashboard_item_type and rec.eagle_dashboard_item_type == 'eagle_kpi' and rec.eagle_model_id:
                eagle_kpi_data = []
                eagle_record_count = 0.0
                eagle_kpi_data_model_1 = {}
                eagle_record_count = rec.eagle_record_count
                eagle_kpi_data_model_1['model'] = rec.eagle_model_name
                eagle_kpi_data_model_1['record_field'] = rec.eagle_record_field.field_description
                eagle_kpi_data_model_1['record_data'] = eagle_record_count

                if rec.eagle_goal_enable:
                    eagle_kpi_data_model_1['target'] = rec.eagle_standard_goal_value
                eagle_kpi_data.append(eagle_kpi_data_model_1)

                if rec.eagle_previous_period:
                    eagle_previous_period_data = rec.eagle_get_previous_period_data(rec)
                    eagle_kpi_data_model_1['previous_period'] = eagle_previous_period_data

                if rec.eagle_model_id_2 and rec.eagle_record_count_type_2:
                    eagle_kpi_data_model_2 = {}
                    eagle_kpi_data_model_2['model'] = rec.eagle_model_name_2
                    eagle_kpi_data_model_2[
                        'record_field'] = 'count' if rec.eagle_record_count_type_2 == 'count' else rec.eagle_record_field_2.field_description
                    eagle_kpi_data_model_2['record_data'] = rec.eagle_record_count_2
                    eagle_kpi_data.append(eagle_kpi_data_model_2)

                rec.eagle_kpi_data = json.dumps(eagle_kpi_data)
            else:
                rec.eagle_kpi_data = False

    # writing separate function for fetching previous period data
    def eagle_get_previous_period_data(self, rec):
        switcher = {
            'l_day': "eagle_get_date('ls_day')",
            't_week': "eagle_get_date('ls_week')",
            't_month': "eagle_get_date('ls_month')",
            't_quarter': "eagle_get_date('ls_quarter')",
            't_year': "eagle_get_date('ls_year')",
        }

        if rec.eagle_date_filter_selection == "l_none":
            date_filter_selection = rec.eagle_dashboard_board_id.eagle_date_filter_selection
        else:
            date_filter_selection = rec.eagle_date_filter_selection
        eagle_date_data = eval(switcher.get(date_filter_selection, "False"))

        if (eagle_date_data):
            previous_period_start_date = eagle_date_data["selected_start_date"]
            previous_period_end_date = eagle_date_data["selected_end_date"]
            proper_domain = rec.eagle_get_previous_period_domain(rec.eagle_domain, previous_period_start_date,
                                                              previous_period_end_date, rec.eagle_date_filter_field)
            eagle_record_count = 0.0

            if rec.eagle_record_count_type == 'count':
                eagle_record_count = self.env[rec.eagle_model_name].search_count(proper_domain)
                return eagle_record_count
            elif rec.eagle_record_field:
                data = self.env[rec.eagle_model_name].read_group(proper_domain, [rec.eagle_record_field.name], [])[0]
                if rec.eagle_record_count_type == 'sum':
                    return data.get(rec.eagle_record_field.name, 0) if data.get('__count', False) and (
                        data.get(rec.eagle_record_field.name)) else 0
                else:
                    return data.get(rec.eagle_record_field.name, 0) / data.get('__count', 1) if data.get('__count',
                                                                                                      False) and (
                                                                                                 data.get(
                                                                                                     rec.eagle_record_field.name)) else 0
            else:
                return False
        else:
            return False

    def eagle_get_previous_period_domain(self, eagle_domain, eagle_start_date, eagle_end_date, date_filter_field):
        if eagle_domain and "%UID" in eagle_domain:
            eagle_domain = eagle_domain.replace('"%UID"', str(self.env.user.id))
        if eagle_domain:
            # try:
            proper_domain = eval(eagle_domain)
            if eagle_start_date and eagle_end_date and date_filter_field:
                proper_domain.extend([(date_filter_field.name, ">=", eagle_start_date),
                                      (date_filter_field.name, "<=", eagle_end_date)])

        else:
            if eagle_start_date and eagle_end_date and date_filter_field:
                proper_domain = ([(date_filter_field.name, ">=", eagle_start_date),
                                  (date_filter_field.name, "<=", eagle_end_date)])
            else:
                proper_domain = []
        return proper_domain

    @api.depends('eagle_domain_2', 'eagle_model_id_2', 'eagle_record_field_2', 'eagle_record_count_type_2', 'eagle_item_start_date_2',
                 'eagle_date_filter_selection_2', 'eagle_record_count_type_2', 'eagle_compare_period_2', 'eagle_year_period_2')
    def eagle_get_record_count_2(self):
        for rec in self:
            if rec.eagle_record_count_type_2 == 'count':
                eagle_record_count = rec.eagle_fetch_model_data_2(rec.eagle_model_name_2, rec.eagle_domain_2, 'search_count', rec)

            elif rec.eagle_record_count_type_2 in ['sum', 'average'] and rec.eagle_record_field_2:
                eagle_records_grouped_data = rec.eagle_fetch_model_data_2(rec.eagle_model_name_2, rec.eagle_domain_2, 'read_group',
                                                                    rec)
                if eagle_records_grouped_data and len(eagle_records_grouped_data) > 0:
                    eagle_records_grouped_data = eagle_records_grouped_data[0]
                    if rec.eagle_record_count_type_2 == 'sum' and eagle_records_grouped_data.get('__count', False) and (
                            eagle_records_grouped_data.get(rec.eagle_record_field_2.name)):
                        eagle_record_count = eagle_records_grouped_data.get(rec.eagle_record_field_2.name, 0)
                    elif rec.eagle_record_count_type_2 == 'average' and eagle_records_grouped_data.get(
                            '__count', False) and (eagle_records_grouped_data.get(rec.eagle_record_field_2.name)):
                        eagle_record_count = eagle_records_grouped_data.get(rec.eagle_record_field_2.name,
                                                                      0) / eagle_records_grouped_data.get('__count',
                                                                                                       1)
                    else:
                        eagle_record_count = 0
                else:
                    eagle_record_count = 0
            else:
                eagle_record_count = False

            rec.eagle_record_count_2 = eagle_record_count

    @api.onchange('eagle_model_id_2')
    def make_record_field_empty_2(self):
        for rec in self:
            rec.eagle_record_field_2 = False
            rec.eagle_domain_2 = False
            rec.eagle_date_filter_field_2 = False
            # To show "created on" by default on date filter field on model select.
            if rec.eagle_model_id:
                datetime_field_list = rec.eagle_date_filter_field_2.search(
                    [('model_id', '=', rec.eagle_model_id.id), '|', ('ttype', '=', 'date'),
                     ('ttype', '=', 'datetime')]).read(['id', 'name'])
                for field in datetime_field_list:
                    if field['name'] == 'create_date':
                        rec.eagle_date_filter_field_2 = field['id']
            else:
                rec.eagle_date_filter_field_2 = False

    # Writing separate function to fetch dashboard item data
    def eagle_fetch_model_data_2(self, eagle_model_name, eagle_domain, eagle_func, rec):
        data = 0
        try:
            if eagle_domain and eagle_domain != '[]' and eagle_model_name:
                proper_domain = self.eagle_convert_into_proper_domain_2(eagle_domain, rec)
                if eagle_func == 'search_count':
                    data = self.env[eagle_model_name].search_count(proper_domain)
                elif eagle_func == 'read_group':
                    data = self.env[eagle_model_name].read_group(proper_domain, [rec.eagle_record_field_2.name], [])
            elif eagle_model_name:
                # Have to put extra if condition here because on load,model giving False value
                proper_domain = self.eagle_convert_into_proper_domain_2(False, rec)
                if eagle_func == 'search_count':
                    data = self.env[eagle_model_name].search_count(proper_domain)

                elif eagle_func == 'read_group':
                    data = self.env[eagle_model_name].read_group(proper_domain, [rec.eagle_record_field_2.name], [])
            else:
                return []
        except Exception as e:
            return []
        return data

    @api.multi
    @api.onchange('eagle_date_filter_selection_2')
    def eagle_set_date_filter_2(self):
        for rec in self:
            if (not rec.eagle_date_filter_selection_2) or rec.eagle_date_filter_selection_2 == "l_none":
                rec.eagle_item_start_date_2 = rec.eagle_item_end_date = False
            elif rec.eagle_date_filter_selection_2 != 'l_custom':
                eagle_date_data = eagle_get_date(rec.eagle_date_filter_selection_2)
                rec.eagle_item_start_date_2 = eagle_date_data["selected_start_date"]
                rec.eagle_item_end_date_2 = eagle_date_data["selected_end_date"]

    def eagle_convert_into_proper_domain_2(self, eagle_domain_2, rec):

        if eagle_domain_2 and "%UID" in eagle_domain_2:
            eagle_domain_2 = eagle_domain_2.replace('"%UID"', str(self.env.user.id))
        if eagle_domain_2 and "%MYCOMPANY" in eagle_domain_2:
            eagle_domain_2 = eagle_domain_2.replace('"%MYCOMPANY"', str(self.env.user.company_id.id))

        eagle_date_domain = False

        if not rec.eagle_date_filter_selection_2 or rec.eagle_date_filter_selection_2 == "l_none":
            selected_start_date = self._context.get('ksDateFilterStartDate', False)
            selected_end_date = self._context.get('ksDateFilterEndDate', False)
            if selected_start_date and selected_end_date and rec.eagle_date_filter_field_2.name:
                eagle_date_domain = [
                    (rec.eagle_date_filter_field_2.name, ">=",
                     selected_start_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT)),
                    (rec.eagle_date_filter_field_2.name, "<=",
                     selected_end_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT))]
        else:
            if rec.eagle_date_filter_selection_2 and rec.eagle_date_filter_selection_2 != 'l_custom':
                eagle_date_data = eagle_get_date(rec.eagle_date_filter_selection_2)
                selected_start_date = eagle_date_data["selected_start_date"]
                selected_end_date = eagle_date_data["selected_end_date"]
            else:
                if rec.eagle_item_start_date_2 or rec.eagle_item_end_date_2:
                    selected_start_date = rec.eagle_item_start_date
                    selected_end_date = rec.eagle_item_end_date

            if selected_start_date and selected_end_date:
                if rec.eagle_compare_period_2:
                    eagle_compare_period_2 = abs(rec.eagle_compare_period_2)
                    if eagle_compare_period_2 > 100:
                        eagle_compare_period_2 = 100
                    if rec.eagle_compare_period_2 > 0:
                        selected_end_date = selected_end_date + (
                                selected_end_date - selected_start_date) * eagle_compare_period_2
                    elif rec.eagle_compare_period_2 < 0:
                        selected_start_date = selected_start_date - (
                                selected_end_date - selected_start_date) * eagle_compare_period_2

                if rec.eagle_year_period_2 and rec.eagle_year_period_2 != 0:
                    abs_year_period_2 = abs(rec.eagle_year_period_2)
                    sign_yp = rec.eagle_year_period_2 / abs_year_period_2
                    if abs_year_period_2 > 10:
                        abs_year_period_2 = 10
                    date_field_name = rec.eagle_date_filter_field_2.name

                    eagle_date_domain = ['&', (date_field_name, ">=", fields.datetime.strftime(selected_start_date,
                                                                                            DEFAULT_SERVER_DATETIME_FORMAT)),
                                      (date_field_name, "<=",
                                       fields.datetime.strftime(selected_end_date, DEFAULT_SERVER_DATETIME_FORMAT))]

                    for p in range(1, abs_year_period_2 + 1):
                        eagle_date_domain.insert(0, '|')
                        eagle_date_domain.extend(['&', (date_field_name, ">=", fields.datetime.strftime(
                            selected_start_date - relativedelta.relativedelta(years=p) * sign_yp,
                            DEFAULT_SERVER_DATETIME_FORMAT)),
                                               (date_field_name, "<=", fields.datetime.strftime(
                                                   selected_end_date - relativedelta.relativedelta(
                                                       years=p) * sign_yp,
                                                   DEFAULT_SERVER_DATETIME_FORMAT))])
                else:
                    if rec.eagle_date_filter_field_2:
                        selected_start_date = fields.datetime.strftime(selected_start_date,
                                                                       DEFAULT_SERVER_DATETIME_FORMAT)
                        selected_end_date = fields.datetime.strftime(selected_end_date,
                                                                     DEFAULT_SERVER_DATETIME_FORMAT)
                        eagle_date_domain = [(rec.eagle_date_filter_field_2.name, ">=", selected_start_date),
                                          (rec.eagle_date_filter_field_2.name, "<=", selected_end_date)]
                    else:
                        eagle_date_domain = []

        proper_domain = eval(eagle_domain_2) if eagle_domain_2 else []
        if eagle_date_domain:
            proper_domain.extend(eagle_date_domain)

        return proper_domain

    @api.model
    def eagle_fetch_chart_data(self, eagle_model_name, eagle_chart_domain, eagle_chart_measure_field, eagle_chart_measure_field_2,
                            eagle_chart_groupby_relation_field, eagle_chart_date_groupby, eagle_chart_groupby_type, orderby,
                            limit, chart_count, eagle_chart_measure_field_ids, eagle_chart_measure_field_2_ids,
                            eagle_chart_groupby_relation_field_id, eagle_chart_data):

        if eagle_chart_groupby_type == "date_type":
            eagle_chart_groupby_field = eagle_chart_groupby_relation_field + ":" + eagle_chart_date_groupby
        else:
            eagle_chart_groupby_field = eagle_chart_groupby_relation_field

        try:
            eagle_chart_records = self.env[eagle_model_name].read_group(eagle_chart_domain, set(
                eagle_chart_measure_field + eagle_chart_measure_field_2 + [eagle_chart_groupby_relation_field]),
                                                                  [eagle_chart_groupby_field],
                                                                  orderby=orderby, limit=limit)
        except Exception as e:
            eagle_chart_records = []
            pass

        if eagle_chart_groupby_type == "relational_type":
            eagle_chart_data['groupByIds'] = []

        for res in eagle_chart_records:

            if all(measure_field in res for measure_field in eagle_chart_measure_field):
                if eagle_chart_groupby_type == "relational_type":
                    if res[eagle_chart_groupby_field]:
                        eagle_chart_data['labels'].append(res[eagle_chart_groupby_field][1]._value)
                        eagle_chart_data['groupByIds'].append(res[eagle_chart_groupby_field][0])
                    else:
                        eagle_chart_data['labels'].append(res[eagle_chart_groupby_field])
                elif eagle_chart_groupby_type == "selection":
                    selection = res[eagle_chart_groupby_field]
                    if selection:
                        eagle_chart_data['labels'].append(
                            dict(self.env[eagle_model_name].fields_get(allfields=[eagle_chart_groupby_field])
                                [eagle_chart_groupby_field]['selection'])[selection])
                    else:
                        eagle_chart_data['labels'].append(selection)
                else:
                    eagle_chart_data['labels'].append(res[eagle_chart_groupby_field])
                eagle_chart_data['domains'].append(res.get('__domain', []))

                counter = 0
                if eagle_chart_measure_field:
                    if eagle_chart_measure_field_2:
                        index = 0
                        for field_rec in eagle_chart_measure_field_2:
                            eagle_groupby_equal_measures = res[eagle_chart_groupby_relation_field + "_count"] \
                                if eagle_chart_measure_field_2_ids[index] == eagle_chart_groupby_relation_field_id \
                                else 1
                            data = res[field_rec] * eagle_groupby_equal_measures \
                                if chart_count == 'sum' else \
                                res[field_rec] * eagle_groupby_equal_measures / \
                                res[eagle_chart_groupby_relation_field + "_count"]
                            eagle_chart_data['datasets'][counter]['data'].append(data)
                            counter += 1
                            index += 1

                    index = 0
                    for field_rec in eagle_chart_measure_field:
                        eagle_groupby_equal_measures = res[eagle_chart_groupby_relation_field + "_count"] \
                            if eagle_chart_measure_field_ids[index] == eagle_chart_groupby_relation_field_id \
                            else 1
                        data = res[field_rec] * eagle_groupby_equal_measures \
                            if chart_count == 'sum' else \
                            res[field_rec] * eagle_groupby_equal_measures / \
                            res[eagle_chart_groupby_relation_field + "_count"]
                        eagle_chart_data['datasets'][counter]['data'].append(data)
                        counter += 1
                        index += 1

                else:
                    data = res[eagle_chart_groupby_relation_field + "_count"]
                    eagle_chart_data['datasets'][0]['data'].append(data)

        return eagle_chart_data

    @api.model
    def eagle_fetch_drill_down_data(self, item_id, domain, sequence):

        record = self.browse(int(item_id))
        eagle_chart_data = {'labels': [], 'datasets': [], 'eagle_show_second_y_scale': False, 'domains': [],
                         'previous_domain': domain, 'eagle_currency': 0, 'eagle_field': "", 'eagle_selection': ""}
        if record.eagle_unit and record.eagle_unit_selection == 'monetary':
            eagle_chart_data['eagle_selection'] += record.eagle_unit_selection
            eagle_chart_data['eagle_currency'] += record.env.user.company_id.currency_id.id
        elif record.eagle_unit and record.eagle_unit_selection == 'custom':
            eagle_chart_data['eagle_selection'] += record.eagle_unit_selection
            if record.eagle_chart_unit:
                eagle_chart_data['eagle_field'] += record.eagle_chart_unit

        # If count chart data type:
        action_lines = record.eagle_action_lines.sorted(key=lambda r: r.sequence)
        action_line = action_lines[sequence]
        eagle_chart_type = action_line.eagle_chart_type if action_line.eagle_chart_type else record.eagle_dashboard_item_type
        eagle_list_view_data = {'label': [],
                             'data_rows': [], 'model': record.eagle_model_name, 'previous_domain': domain, }
        if action_line.eagle_chart_type == 'eagle_list_view':
            if record.eagle_dashboard_item_type == 'eagle_list_view':
                eagle_chart_list_measure = record.eagle_list_view_group_fields
            else :
                eagle_chart_list_measure = record.eagle_chart_measure_field

            eagle_list_fields = []
            orderby = action_line.eagle_sort_by_field.name if action_line.eagle_sort_by_field else "id"
            if action_line.eagle_sort_by_order:
                orderby = orderby + " " + action_line.eagle_sort_by_order
            limit = action_line.eagle_record_limit if action_line.eagle_record_limit \
                                                   and action_line.eagle_record_limit > 0 else False
            eagle_count = 0
            for ks in record.eagle_action_lines:
                eagle_count += 1
            if action_line.eagle_item_action_field.ttype == 'many2one':
                eagle_list_view_data['groupby'] = action_line.eagle_item_action_field.name
                eagle_list_fields.append(action_line.eagle_item_action_field.name)
                eagle_list_view_data['label'].append(action_line.eagle_item_action_field.field_description)
                for res in eagle_chart_list_measure:
                    eagle_list_fields.append(res.name)
                    eagle_list_view_data['label'].append(res.field_description)

                eagle_list_view_records = self.env[record.eagle_model_name].read_group(domain, eagle_list_fields,
                                                                                 [action_line.eagle_item_action_field.name],
                                                                                 orderby=orderby, limit=limit)
                for res in eagle_list_view_records:

                    counter = 0
                    data_row = {'id': res[action_line.eagle_item_action_field.name][0], 'data': [],
                                'domain': json.dumps(res['__domain']), 'sequence': sequence + 1,
                                'last_seq': eagle_count}
                    for field_rec in eagle_list_fields:
                        if counter == 0:
                            data_row['data'].append(res[field_rec][1]._value)
                        else:
                            data_row['data'].append(res[field_rec])
                        counter += 1
                    eagle_list_view_data['data_rows'].append(data_row)

            elif action_line.eagle_item_action_field.ttype == 'date' or \
                    action_line.eagle_item_action_field.ttype == 'datetime':
                eagle_list_view_data['list_view_type'] = 'date_type'
                eagle_list_field = []
                eagle_list_view_data['groupby'] = action_line.eagle_item_action_field.name
                eagle_list_field.append(action_line.eagle_item_action_field.name  + ':' + action_line.eagle_item_action_date_groupby)
                eagle_list_fields.append(action_line.eagle_item_action_field.name)
                eagle_list_view_data['label'].append(
                    action_line.eagle_item_action_field.field_description)
                for res in eagle_chart_list_measure:
                    eagle_list_fields.append(res.name)
                    eagle_list_field.append(res.name)
                    eagle_list_view_data['label'].append(res.field_description)

                eagle_list_view_records = self.env[record.eagle_model_name].read_group(domain, eagle_list_fields,
                                                                                 [action_line.eagle_item_action_field.name
                                                                                  + ':' + action_line.eagle_item_action_date_groupby],
                                                                                 orderby=orderby, limit=limit)

                for res in eagle_list_view_records:
                    counter = 0
                    data_row = { 'data': [],
                                'domain': json.dumps(res['__domain']), 'sequence': sequence + 1,
                                'last_seq': eagle_count}
                    for field_rec in eagle_list_field:
                        data_row['data'].append(res[field_rec])
                    eagle_list_view_data['data_rows'].append(data_row)

            elif action_line.eagle_item_action_field.ttype == 'selection':
                eagle_list_view_data['list_view_type'] = 'selection'
                eagle_list_view_data['groupby'] = action_line.eagle_item_action_field.name
                eagle_selection_field = action_line.eagle_item_action_field.name
                eagle_list_view_data['label'].append(action_line.eagle_item_action_field.field_description)
                for res in eagle_chart_list_measure:
                    eagle_list_fields.append(res.name)
                    eagle_list_view_data['label'].append(res.field_description)

                eagle_list_view_records = self.env[record.eagle_model_name].read_group(domain, eagle_list_fields,
                                                                                 [
                                                                                     action_line.eagle_item_action_field.name],
                                                                                 orderby=orderby, limit=limit)
                for res in eagle_list_view_records:
                    counter = 0
                    data_row = { 'data': [],
                                'domain': json.dumps(res['__domain']), 'sequence': sequence + 1,
                                'last_seq': eagle_count}
                    if res[eagle_selection_field]:
                        data_row['data'].append(dict(
                            self.env[record.eagle_model_name].fields_get(allfields=eagle_selection_field)
                            [eagle_selection_field]['selection'])[res[eagle_selection_field]])
                    else:
                        data_row['data'].append(" ")
                    for field_rec in eagle_list_fields:
                        data_row['data'].append(res[field_rec])
                    eagle_list_view_data['data_rows'].append(data_row)

            else:
                eagle_list_view_data['list_view_type'] = 'other'
                eagle_list_view_data['groupby'] = action_line.eagle_item_action_field.name
                eagle_list_fields.append(action_line.eagle_item_action_field.name)
                eagle_list_view_data['label'].append(action_line.eagle_item_action_field.field_description)
                for res in eagle_chart_list_measure:
                    eagle_list_fields.append(res.name)
                    eagle_list_view_data['label'].append(res.field_description)

                eagle_list_view_records = self.env[record.eagle_model_name].read_group(domain, eagle_list_fields,
                                                                                 [
                                                                                     action_line.eagle_item_action_field.name],
                                                                                 orderby=orderby, limit=limit)
                for res in eagle_list_view_records:
                    if all(list_fields in res for list_fields in eagle_list_fields):
                        counter = 0
                        data_row = {'id': action_line.eagle_item_action_field.name, 'data': [],
                                    'domain': json.dumps(res['__domain']), 'sequence': sequence + 1,
                                    'last_seq': eagle_count}

                        for field_rec in eagle_list_fields:
                            if counter == 0:
                                data_row['data'].append(res[field_rec])
                            else:
                                if action_line.eagle_item_action_field.name == field_rec:
                                    data_row['data'].append(res[field_rec] * res[field_rec + '_count'])
                                else:
                                    data_row['data'].append(res[field_rec])
                            counter += 1
                        eagle_list_view_data['data_rows'].append(data_row)


            return { "eagle_list_view_data": json.dumps(eagle_list_view_data), "eagle_list_view_type": "grouped",
                    'sequence': sequence + 1,}
        else:
            eagle_chart_measure_field = []
            eagle_chart_measure_field_ids = []
            eagle_chart_measure_field_2 = []
            eagle_chart_measure_field_2_ids = []
            if record.eagle_chart_data_count_type == "count":
                eagle_chart_data['datasets'].append({'data': [], 'label': "Count"})
            else:
                if eagle_chart_type == 'eagle_bar_chart':
                    if record.eagle_chart_measure_field_2:
                        eagle_chart_data['eagle_show_second_y_scale'] = True

                    for res in record.eagle_chart_measure_field_2:
                        eagle_chart_measure_field_2.append(res.name)
                        eagle_chart_measure_field_2_ids.append(res.id)
                        eagle_chart_data['datasets'].append(
                            {'data': [], 'label': res.field_description, 'type': 'line', 'yAxisID': 'y-axis-1'})
                if record.eagle_dashboard_item_type == 'eagle_list_view':
                    for res in record.eagle_list_view_group_fields:
                        eagle_chart_measure_field.append(res.name)
                        eagle_chart_measure_field_ids.append(res.id)
                        eagle_chart_data['datasets'].append({'data': [], 'label': res.field_description})
                else:
                    for res in record.eagle_chart_measure_field:
                        eagle_chart_measure_field.append(res.name)
                        eagle_chart_measure_field_ids.append(res.id)
                        eagle_chart_data['datasets'].append({'data': [], 'label': res.field_description})

            eagle_chart_groupby_relation_field = action_line.eagle_item_action_field.name
            eagle_chart_relation_type = action_line.eagle_item_action_field_type
            eagle_chart_date_group_by = action_line.eagle_item_action_date_groupby
            eagle_chart_groupby_relation_field_id = action_line.eagle_item_action_field.id
            orderby = action_line.eagle_sort_by_field.name if action_line.eagle_sort_by_field else "id"
            if action_line.eagle_sort_by_order:
                orderby = orderby + " " + action_line.eagle_sort_by_order
            limit = action_line.eagle_record_limit if action_line.eagle_record_limit and action_line.eagle_record_limit > 0 else False

            if eagle_chart_type != "eagle_bar_chart":
                eagle_chart_measure_field_2 = []
                eagle_chart_measure_field_2_ids = []

            eagle_chart_data = record.eagle_fetch_chart_data(record.eagle_model_name, domain, eagle_chart_measure_field,
                                                       eagle_chart_measure_field_2,
                                                       eagle_chart_groupby_relation_field, eagle_chart_date_group_by,
                                                       eagle_chart_relation_type,
                                                       orderby, limit, record.eagle_chart_data_count_type,
                                                       eagle_chart_measure_field_ids,
                                                       eagle_chart_measure_field_2_ids, eagle_chart_groupby_relation_field_id,
                                                       eagle_chart_data)

            return {
                'eagle_chart_data': json.dumps(eagle_chart_data),
                'eagle_chart_type': eagle_chart_type,
                'sequence': sequence + 1,
            }

    @api.model
    def eagle_get_start_end_date(self, model_name, eagle_chart_groupby_relation_field, ttype, eagle_chart_domain,
                              eagle_goal_domain):
        eagle_start_end_date = {}
        try:
            model_field_start_date = \
                self.env[model_name].search(eagle_chart_domain + [(eagle_chart_groupby_relation_field, '!=', False)], limit=1,
                                            order=eagle_chart_groupby_relation_field + " ASC")[
                    eagle_chart_groupby_relation_field]
            model_field_end_date = \
                self.env[model_name].search(eagle_chart_domain + [(eagle_chart_groupby_relation_field, '!=', False)], limit=1,
                                            order=eagle_chart_groupby_relation_field + " DESC")[
                    eagle_chart_groupby_relation_field]
        except Exception as e:
            model_field_start_date = model_field_end_date = False
            pass

        goal_model_start_date = \
            self.env['eagle_dashboard.item_goal'].search(eagle_goal_domain, limit=1,
                                                            order='eagle_goal_date ASC')['eagle_goal_date']
        goal_model_end_date = \
            self.env['eagle_dashboard.item_goal'].search(eagle_goal_domain, limit=1,
                                                            order='eagle_goal_date DESC')['eagle_goal_date']

        if model_field_start_date and ttype == "date":
            model_field_end_date = datetime.combine(model_field_end_date, datetime.min.time())
            model_field_start_date = datetime.combine(model_field_start_date, datetime.min.time())

        if model_field_start_date and goal_model_start_date:
            goal_model_start_date = datetime.combine(goal_model_start_date, datetime.min.time())
            goal_model_end_date = datetime.combine(goal_model_end_date, datetime.max.time())
            if model_field_start_date < goal_model_start_date:
                eagle_start_end_date['start_date'] = model_field_start_date.strftime("%Y-%m-%d 00:00:00")
            else:
                eagle_start_end_date['start_date'] = goal_model_start_date.strftime("%Y-%m-%d 00:00:00")
            if model_field_end_date > goal_model_end_date:
                eagle_start_end_date['end_date'] = model_field_end_date.strftime("%Y-%m-%d 23:59:59")
            else:
                eagle_start_end_date['end_date'] = goal_model_end_date.strftime("%Y-%m-%d 23:59:59")

        elif model_field_start_date and not goal_model_start_date:
            eagle_start_end_date['start_date'] = model_field_start_date.strftime("%Y-%m-%d 00:00:00")
            eagle_start_end_date['end_date'] = model_field_end_date.strftime("%Y-%m-%d 23:59:59")

        elif goal_model_start_date and not model_field_start_date:
            eagle_start_end_date['start_date'] = goal_model_start_date.strftime("%Y-%m-%d 00:00:00")
            eagle_start_end_date['end_date'] = goal_model_start_date.strftime("%Y-%m-%d 23:59:59")
        else:
            eagle_start_end_date['start_date'] = False
            eagle_start_end_date['end_date'] = False

        return eagle_start_end_date

     #List View pagination
    @api.model
    def eagle_get_next_offset(self, eagle_item_id, offset):
        record = self.browse(eagle_item_id)
        eagle_offset = offset['offset']
        eagle_list_view_data = self.eagle_fetch_list_view_data(record,offset=int(eagle_offset))

        return {
            'eagle_list_view_data': json.dumps(eagle_list_view_data),
            'offset': int(eagle_offset) + 1,
            'next_offset': int(eagle_offset) + len(eagle_list_view_data['data_rows']),
        }


    @api.model
    def get_sorted_month(self, display_format, ftype='date'):
        query = """
                    with d as (SELECT date_trunc(%(aggr)s, generate_series) AS timestamp FROM generate_series
                    (%(timestamp_begin)s::TIMESTAMP , %(timestamp_end)s::TIMESTAMP , %(aggr1)s::interval ))
                     select timestamp from d group by timestamp order by timestamp
                        """
        self.env.cr.execute(query, {
            'timestamp_begin': "2020-01-01 00:00:00",
            'timestamp_end': "2020-12-31 00:00:00",
            'aggr': 'month',
            'aggr1': '1 month'
        })

        dates = self.env.cr.fetchall()
        locale = self._context.get('lang') or 'en_US'
        tz_convert = self._context.get('tz')
        return [self.format_label(d[0], ftype, display_format, tz_convert, locale) for d in dates]

    # Fix Order BY : maybe revert old code
    @api.model
    def generate_timeserise(self, date_begin, date_end, aggr, ftype='date'):
        query = """
                    with d as (SELECT date_trunc(%(aggr)s, generate_series) AS timestamp FROM generate_series
                    (%(timestamp_begin)s::TIMESTAMP , %(timestamp_end)s::TIMESTAMP , '1 hour'::interval )) 
                    select timestamp from d group by timestamp order by timestamp
                """

        self.env.cr.execute(query, {
            'timestamp_begin': date_begin,
            'timestamp_end': date_end,
            'aggr': aggr,
            'aggr1': '1 ' + aggr
        })
        dates = self.env.cr.fetchall()
        display_formats = {
            # Careful with week/year formats:
            #  - yyyy (lower) must always be used, except for week+year formats
            #  - YYYY (upper) must always be used for week+year format
            #         e.g. 2006-01-01 is W52 2005 in some locales (de_DE),
            #                         and W1 2006 for others
            #
            # Mixing both formats, e.g. 'MMM YYYY' would yield wrong results,
            # such as 2006-01-01 being formatted as "January 2005" in some locales.
            # Cfr: http://babel.pocoo.org/en/latest/dates.html#date-fields
            'minute': 'hh:mm dd MMM',
            'hour': 'hh:00 dd MMM',
            'day': 'dd MMM yyyy',  # yyyy = normal year
            'week': "'W'w YYYY",  # w YYYY = ISO week-year
            'month': 'MMMM yyyy',
            'quarter': 'QQQ yyyy',
            'year': 'yyyy',
        }

        display_format = display_formats[aggr]
        locale = self._context.get('lang') or 'en_US'
        tz_convert = self._context.get('tz')
        return [self.format_label(d[0], ftype, display_format, tz_convert, locale) for d in dates]

    @api.model
    def format_label(self, value, ftype, display_format, tz_convert, locale):

        tzinfo = None
        if ftype == 'datetime':

            if tz_convert:
                value = pytz.timezone(self._context['tz']).localize(value)
                tzinfo = value.tzinfo
            return babel.dates.format_datetime(value, format=display_format, tzinfo=tzinfo, locale=locale)
        else:

            if tz_convert:
                value = pytz.timezone(self._context['tz']).localize(value)
                tzinfo = value.tzinfo
            return babel.dates.format_date(value, format=display_format, locale=locale)

    def eagle_sort_sub_group_by_records(self, eagle_data, field_type, eagle_chart_date_groupby, eagle_sort_by_order,
                                     eagle_chart_date_sub_groupby):
        if eagle_data:
            reverse = False
            if eagle_sort_by_order == 'DESC':
                reverse = True

            for data in eagle_data:
                if field_type == 'date_type':
                    if eagle_chart_date_groupby in ['minute', 'hour']:
                        if eagle_chart_date_sub_groupby in ["month", "week", "quarter", "year"]:
                            eagle_sorted_months = self.get_sorted_month("MMM")
                            data['value'].sort(key=lambda x: int(
                                str(eagle_sorted_months.index(x['x'].split(" ")[2]) + 1) + x['x'].split(" ")[1] +
                                x['x'].split(" ")[0].replace(":", "")), reverse=reverse)
                        else:
                            data['value'].sort(key=lambda x: int(x['x'].replace(":", "")), reverse=reverse)
                    elif eagle_chart_date_groupby == 'day' and eagle_chart_date_sub_groupby in ["quarter", "year"]:
                        eagle_sorted_days = self.generate_timeserise("2020-01-01 00:00:00", "2020-12-31 00:00:00",
                                                                  'day', "date")
                        b = [" ".join(x.split(" ")[0:2]) for x in eagle_sorted_days]
                        data['value'].sort(key=lambda x: b.index(x['x']), reverse=reverse)
                    elif eagle_chart_date_groupby == 'day' and eagle_chart_date_sub_groupby not in ["quarter", "year"]:
                        data['value'].sort(key=lambda i: int(i['x']), reverse=reverse)
                    elif eagle_chart_date_groupby == 'week':
                        data['value'].sort(key=lambda i: int(i['x'][1:]), reverse=reverse)
                    elif eagle_chart_date_groupby == 'month':
                        eagle_sorted_months = self.generate_timeserise("2020-01-01 00:00:00", "2020-12-31 00:00:00",
                                                                    'month', "date")
                        b = [" ".join(x.split(" ")[0:1]) for x in eagle_sorted_months]
                        data['value'].sort(key=lambda x: b.index(x['x']), reverse=reverse)
                    elif eagle_chart_date_groupby == 'quarter':
                        data['value'].sort(key=lambda i: int(i['x'][1:]), reverse=reverse)
                    elif eagle_chart_date_groupby == 'year':
                        data['value'].sort(key=lambda i: int(i['x']), reverse=reverse)
                else:
                    data['value'].sort(key=lambda i: i['x'], reverse=reverse)

        return eagle_data

    @api.onchange('eagle_domain_2')
    def eagle_onchange_check_domain_2_onchange(self):
        if self.eagle_domain_2:
            proper_domain_2 = []
            try:
                eagle_domain_2 = self.eagle_domain_2
                if "%UID" in eagle_domain_2:
                    eagle_domain_2 = eagle_domain_2.replace("%UID", str(self.env.user.id))
                if "%MYCOMPANY" in eagle_domain_2:
                    eagle_domain_2 = eagle_domain_2.replace("%MYCOMPANY", str(self.env.user.company_id.id))
                eagle_domain_2 = safe_eval(eagle_domain_2)

                for element in eagle_domain_2:
                    proper_domain_2.append(element) if type(element) != list else proper_domain_2.append(tuple(element))
                self.env[self.eagle_model_name_2].search_count(proper_domain_2)
            except Exception:
                raise UserError("Invalid Domain")

    @api.onchange('eagle_domain')
    def eagle_onchange_check_domain_onchange(self):
        if self.eagle_domain:
            proper_domain = []
            try:
                eagle_domain = self.eagle_domain
                if "%UID" in eagle_domain:
                    eagle_domain = eagle_domain.replace("%UID", str(self.env.user.id))
                if "%MYCOMPANY" in eagle_domain:
                    eagle_domain = eagle_domain.replace("%MYCOMPANY", str(self.env.user.company_id.id))
                eagle_domain = safe_eval(eagle_domain)
                for element in eagle_domain:
                    proper_domain.append(element) if type(element) != list else proper_domain.append(tuple(element))
                self.env[self.eagle_model_name].search_count(proper_domain)
            except Exception as e:
                raise UserError("Invalid Domain")


class KsDashboardItemsGoal(models.Model):
    _name = 'eagle_dashboard.item_goal'
    _description = 'Eagle Dashboard Items Goal Lines'

    eagle_goal_date = fields.Date(string="Date")
    eagle_goal_value = fields.Float(string="Value")

    eagle_dashboard_item = fields.Many2one('eagle_dashboard.item', string="Dashboard Item")


class KsDashboardItemsActions(models.Model):
    _name = 'eagle_dashboard.item_action'
    _description = 'Eagle Dashboard Items Action Lines'

    eagle_item_action_field = fields.Many2one('ir.model.fields',
                                           domain="[('model_id','=',eagle_model_id),('name','!=','id'),('store','=',True),"
                                                  "('ttype','!=','binary'),('ttype','!=','many2many'), "
                                                  "('ttype','!=','one2many')]",
                                           string="Action Group By")

    eagle_item_action_field_type = fields.Char(compute="eagle_get_item_action_type")

    eagle_item_action_date_groupby = fields.Selection([('minute', 'Minute'),
                                                    ('hour', 'Hour'),
                                                    ('day', 'Day'),
                                                    ('week', 'Week'),
                                                    ('month', 'Month'),
                                                    ('quarter', 'Quarter'),
                                                    ('year', 'Year'),
                                                    ], string="Group By Date")

    eagle_chart_type = fields.Selection([('eagle_bar_chart', 'Bar Chart'),
                                      ('eagle_horizontalBar_chart', 'Horizontal Bar Chart'),
                                      ('eagle_line_chart', 'Line Chart'),
                                      ('eagle_area_chart', 'Area Chart'),
                                      ('eagle_pie_chart', 'Pie Chart'),
                                      ('eagle_doughnut_chart', 'Doughnut Chart'),
                                      ('eagle_polarArea_chart', 'Polar Area Chart'),
                                      ('eagle_list_view', 'List View')],
                                     string="Item Type")

    eagle_dashboard_item_id = fields.Many2one('eagle_dashboard.item', string="Dashboard Item")
    eagle_model_id = fields.Many2one('ir.model', related='eagle_dashboard_item_id.eagle_model_id')
    sequence = fields.Integer(string="Sequence")
    # For sorting and record limit
    eagle_record_limit = fields.Integer(string="Record Limit")
    eagle_sort_by_field = fields.Many2one('ir.model.fields',
                                       domain="[('model_id','=',eagle_model_id),('name','!=','id'),('store','=',True),"
                                              "('ttype','!=','one2many'),('ttype','!=','binary')]",
                                       string="Sort By Field")
    eagle_sort_by_order = fields.Selection([('ASC', 'Ascending'), ('DESC', 'Descending')],
                                        string="Sort Order")

    @api.depends('eagle_item_action_field')
    def eagle_get_item_action_type(self):
        for rec in self:
            if rec.eagle_item_action_field.ttype == 'datetime' or rec.eagle_item_action_field.ttype == 'date':
                rec.eagle_item_action_field_type = 'date_type'
            elif rec.eagle_item_action_field.ttype == 'many2one':
                rec.eagle_item_action_field_type = 'relational_type'
                rec.eagle_item_action_date_groupby = False
            elif rec.eagle_item_action_field.ttype == 'selection':
                rec.eagle_item_action_field_type = 'selection'
                rec.eagle_item_action_date_groupby = False
            else:
                rec.eagle_item_action_field_type = 'none'
                rec.eagle_item_action_date_groupby = False

    @api.onchange('eagle_item_action_date_groupby')
    def eagle_check_date_group_by(self):
        for rec in self:
            if rec.eagle_item_action_field.ttype == 'date' and rec.eagle_item_action_date_groupby in ['hour', 'minute']:
                raise ValidationError(_('Action field: {} cannot be aggregated by {}').format(
                    rec.eagle_item_action_field.display_name, rec.eagle_item_action_date_groupby))
