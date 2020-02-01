eagle.define('eagle_dashboard_list.eagle_color_picker', function (require) {
    "use strict";

    require('web.dom_ready');

    var registry = require('web.field_registry');
    var AbstractField = require('web.AbstractField');
    var core = require('web.core');

    var QWeb = core.qweb;

    //Widget for color picker being used in dashboard item create view.
    //TODO : This color picker functionality can be improved a lot.
    var KsColorPicker = AbstractField.extend({

        supportedFieldTypes: ['char'],

        events: _.extend({}, AbstractField.prototype.events, {
            'change.spectrum .eagle_color_picker': '_ksOnColorChange',
            'change .eagle_color_opacity': '_ksOnOpacityChange',
            'input .eagle_color_opacity': '_ksOnOpacityInput'
        }),

        init: function (parent, state, params) {
            this._super.apply(this, arguments);

            this.jsLibs.push('/eagle_dashboard/static/lib/js/spectrum.js');

            this.cssLibs.push('/eagle_dashboard/static/lib/css/spectrum.css');

        },


        _render: function () {
            this.$el.empty();
            var eagle_color_value = '#376CAE';
            var eagle_color_opacity = '0.99';
            if (this.value) {
                eagle_color_value = this.value.split(',')[0];
                eagle_color_opacity = this.value.split(',')[1];
            };
            var $view = $(QWeb.render('eagle_color_picker_opacity_view', {
                eagle_color_value: eagle_color_value,
                eagle_color_opacity: eagle_color_opacity
            }));

            this.$el.append($view)

            this.$el.find(".eagle_color_picker").spectrum({
                color: eagle_color_value,
                showInput: true,
                hideAfterPaletteSelect: true,

                clickoutFiresChange: true,
                showInitial: true,
                preferredFormat: "rgb",
            });

            if (this.mode === 'readonly') {
                this.$el.find('.eagle_color_picker').addClass('eagle_not_click');
                this.$el.find('.eagle_color_opacity').addClass('eagle_not_click');
                this.$el.find('.eagle_color_picker').spectrum("disable");
            } else {
                this.$el.find('.eagle_color_picker').spectrum("enable");
            }
        },



        _ksOnColorChange: function (e, tinycolor) {
            this._setValue(tinycolor.toHexString().concat("," + this.value.split(',')[1]));
        },

        _ksOnOpacityChange: function (event) {
            this._setValue(this.value.split(',')[0].concat("," + event.currentTarget.value));
        },

        _ksOnOpacityInput: function (event) {
            var self = this;
            var color;
            if (self.name == "eagle_background_color") {
                color = $('.eagle_db_item_preview_color_picker').css("background-color")
                $('.eagle_db_item_preview_color_picker').css("background-color", self.get_color_opacity_value(color, event.currentTarget.value))

                color = $('.eagle_db_item_preview_l2').css("background-color")
                $('.eagle_db_item_preview_l2').css("background-color", self.get_color_opacity_value(color, event.currentTarget.value))

            } else if (self.name == "eagle_default_icon_color") {
                color = $('.eagle_dashboard_icon_color_picker > span').css('color')
                $('.eagle_dashboard_icon_color_picker > span').css('color', self.get_color_opacity_value(color, event.currentTarget.value))
            } else if (self.name == "eagle_font_color") {
                color = $('.eagle_db_item_preview').css("color")
                color = $('.eagle_db_item_preview').css("color", self.get_color_opacity_value(color, event.currentTarget.value))
            }
        },

        get_color_opacity_value: function (color, val) {
            if (color) {
                return color.replace(color.split(',')[3], val + ")");
            } else {
                return false;
            }
        },


    });
    registry.add('eagle_color_dashboard_picker', KsColorPicker);

    return {
        KsColorPicker: KsColorPicker
    };

});