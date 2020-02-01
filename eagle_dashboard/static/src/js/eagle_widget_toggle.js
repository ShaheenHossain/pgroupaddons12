eagle.define('eagle_dashboard_list.eagle_widget_toggle', function (require) {
    "use strict";

    var registry = require('web.field_registry');
    var AbstractField = require('web.AbstractField');
    var core = require('web.core');


    var QWeb = core.qweb;


    var KsWidgetToggle = AbstractField.extend({

        supportedFieldTypes: ['char'],

        events: _.extend({}, AbstractField.prototype.events, {
            'change .eagle_toggle_icon_input': 'eagle_toggle_icon_input_click',
        }),

        _render: function () {
            var self = this;
            self.$el.empty();


            var $view = $(QWeb.render('eagle_widget_toggle'));
            if (self.value) {
                $view.find("input[value='" + self.value + "']").prop("checked", true);
            }
            this.$el.append($view)

            if (this.mode === 'readonly') {
                this.$el.find('.eagle_select_dashboard_item_toggle').addClass('eagle_not_click');
            }
        },

        eagle_toggle_icon_input_click: function (e) {
            var self = this;
            self._setValue(e.currentTarget.value);
        }
    });

    var KsWidgetToggleKPI = AbstractField.extend({

        supportedFieldTypes: ['char'],

        events: _.extend({}, AbstractField.prototype.events, {
            'change .eagle_toggle_icon_input': 'eagle_toggle_icon_input_click',
        }),

        _render: function () {
            var self = this;
            self.$el.empty();


            var $view = $(QWeb.render('eagle_widget_toggle_kpi'));
            if (self.value) {
                $view.find("input[value='" + self.value + "']").prop("checked", true);
            }
            this.$el.append($view)

            if (this.mode === 'readonly') {
                this.$el.find('.eagle_select_dashboard_item_toggle').addClass('eagle_not_click');
            }
        },
        eagle_toggle_icon_input_click: function (e) {
            var self = this;
            self._setValue(e.currentTarget.value);
        }
    });

    var KsWidgetToggleKpiTarget = AbstractField.extend({

        supportedFieldTypes: ['char'],

        events: _.extend({}, AbstractField.prototype.events, {
            'change .eagle_toggle_icon_input': 'eagle_toggle_icon_input_click',
        }),

        _render: function () {
            var self = this;
            self.$el.empty();


            var $view = $(QWeb.render('eagle_widget_toggle_kpi_target_view'));
            if (self.value) {
                $view.find("input[value='" + self.value + "']").prop("checked", true);
            }
            this.$el.append($view)

            if (this.mode === 'readonly') {
                this.$el.find('.eagle_select_dashboard_item_toggle').addClass('eagle_not_click');
            }
        },

        eagle_toggle_icon_input_click: function (e) {
            var self = this;
            self._setValue(e.currentTarget.value);
        }
    });

    registry.add('eagle_widget_toggle', KsWidgetToggle);
    registry.add('eagle_widget_toggle_kpi', KsWidgetToggleKPI);
    registry.add('eagle_widget_toggle_kpi_target', KsWidgetToggleKpiTarget);
    return {
        KsWidgetToggle: KsWidgetToggle,
        KsWidgetToggleKPI: KsWidgetToggleKPI,
        KsWidgetToggleKpiTarget :KsWidgetToggleKpiTarget
    };


});