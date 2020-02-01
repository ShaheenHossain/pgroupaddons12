import io
import json
import operator

from eagle.addons.web.controllers.main import ExportFormat,serialize_exception

from eagle import http
from eagle.http import content_disposition,request


class KsDashboardExport(ExportFormat, http.Controller):

    def base(self, data, token):
        params = json.loads(data)
        header, dashboard_data = operator.itemgetter('header', 'dashboard_data')(params)
        return request.make_response(self.from_data(dashboard_data),
                                     headers=[('Content-Disposition',
                                               content_disposition(self.filename(header))),
                                              ('Content-Type', self.content_type)],
                                     cookies={'fileToken': token})


class KsDashboardJsonExport(KsDashboardExport, http.Controller):

    @http.route('/eagle_dashboard/export/dashboard_json', type='http', auth="user")
    @serialize_exception
    def index(self, data, token):
        return self.base(data, token)

    @property
    def content_type(self):
        return 'text/csv;charset=utf8'

    def filename(self, base):
        return base + '.json'

    def from_data(self, dashboard_data):
        fp = io.StringIO()
        fp.write(json.dumps(dashboard_data))

        return fp.getvalue()

class KsItemJsonExport(KsDashboardExport, http.Controller):

    @http.route('/eagle_dashboard/export/item_json', type='http', auth="user")
    @serialize_exception
    def index(self, data, token):
        data = json.loads(data)
        item_id = data["item_id"]
        data['dashboard_data'] = request.env['eagle_dashboard.board'].eagle_export_item(item_id)
        data = json.dumps(data)
        return self.base(data, token)

    @property
    def content_type(self):
        return 'text/csv;charset=utf8'

    def filename(self, base):
        return base + '.json'

    def from_data(self, dashboard_data):
        fp = io.StringIO()
        fp.write(json.dumps(dashboard_data))

        return fp.getvalue()
