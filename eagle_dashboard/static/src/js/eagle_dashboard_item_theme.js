eagle.define('eagle_dashboard_list.eagle_dashboard_item_theme', function (require) {
    "use strict";

    var registry = require('web.field_registry');
    var AbstractField = require('web.AbstractField');
    var core = require('web.core');

    var QWeb = core.qweb;

    //Widget for dashboard item theme using while creating dashboard item.
    var KsDashboardTheme = AbstractField.extend({

        supportedFieldTypes: ['char'],

        events: _.extend({}, AbstractField.prototype.events, {
            'click .eagle_dashboard_theme_input_container': 'eagle_dashboard_theme_input_container_click',
        }),

        _render: function () {
            var self = this;
            self.$el.empty();
            var $view = $(QWeb.render('eagle_dashboard_theme_view'));
            if (self.value) {
                $view.find("input[value='" + self.value + "']").prop("checked", true);
            }
            self.$el.append($view)

            if (this.mode === 'readonly') {
                this.$el.find('.eagle_dashboard_theme_view_render').addClass('eagle_not_click');
            }
        },

        eagle_dashboard_theme_input_container_click: function (e) {
            var self = this;
            var $box = $(e.currentTarget).find(':input');
            if ($box.is(":checked")) {
                self.$el.find('.eagle_dashboard_theme_input').prop('checked', false)
                $box.prop("checked", true);
            } else {
                $box.prop("checked", false);
            }
            self._setValue($box[0].value);
        },
    });

    registry.add('eagle_dashboard_item_theme', KsDashboardTheme);

    return {
        KsDashboardTheme: KsDashboardTheme
    };

});