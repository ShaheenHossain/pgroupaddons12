eagle.define('eagle_dashboard_list.eagle_image_basic_widget', function (require) {
    "use strict";

    var core = require('web.core');
    var basic_fields = require('web.basic_fields');
    var core = require('web.core');
    var registry = require('web.field_registry');

    var QWeb = core.qweb;

    var KsImageWidget = basic_fields.FieldBinaryImage.extend({

        init: function (parent, state, params) {
            this._super.apply(this, arguments);
            this.ksSelectedIcon = false;
            this.eagle_icon_set = ['home', 'puzzle-piece', 'clock-o', 'comments-o', 'car', 'calendar', 'calendar-times-o', 'bar-chart', 'commenting-o', 'star-half-o', 'address-book-o', 'tachometer', 'search', 'money', 'line-chart', 'area-chart', 'pie-chart', 'check-square-o', 'users', 'shopping-cart', 'truck', 'user-circle-o', 'user-plus', 'sun-o', 'paper-plane', 'rss', 'gears', 'check', 'book'];
        },

        template: 'KsFieldBinaryImage',

        events: _.extend({}, basic_fields.FieldBinaryImage.prototype.events, {
            'click .eagle_icon_container_list': 'eagle_icon_container_list',
            'click .eagle_image_widget_icon_container': 'eagle_image_widget_icon_container',
            'click .eagle_icon_container_open_button': 'eagle_icon_container_open_button',
            'click .eagle_fa_icon_search': 'eagle_fa_icon_search',
            'keyup .eagle_modal_icon_input': 'eagle_modal_icon_input_enter',
        }),

        _render: function () {
            var eagle_self = this;
            var url = this.placeholder;
            if (eagle_self.value) {
                eagle_self.$('> img').remove();
                eagle_self.$('> span').remove();
                $('<span>').addClass('fa fa-' + eagle_self.recordData.eagle_default_icon + ' fa-5x').appendTo(eagle_self.$el).css('color', 'black');
            } else {
                var $img = $(QWeb.render("FieldBinaryImage-img", {
                    widget: this,
                    url: url
                }));
                eagle_self.$('> img').remove();
                eagle_self.$('> span').remove();
                eagle_self.$el.prepend($img);
            }

            var $eagle_icon_container_modal = $(QWeb.render('eagle_icon_container_modal_template', {
                eagle_fa_icons_set: eagle_self.eagle_icon_set
            }));

            $eagle_icon_container_modal.prependTo(eagle_self.$el);
        },

        //This will show modal box on clicking on open icon button.
        eagle_image_widget_icon_container: function (e) {
            $('#eagle_icon_container_modal_id').modal({
                show: true,
            });

        },


        eagle_icon_container_list: function (e) {
            var self = this;
            self.ksSelectedIcon = $(e.currentTarget).find('span').attr('id').split('.')[1]
            _.each($('.eagle_icon_container_list'), function (selected_icon) {
                $(selected_icon).removeClass('eagle_icon_selected');
            });

            $(e.currentTarget).addClass('eagle_icon_selected')
            $('.eagle_icon_container_open_button').show()
        },

        //Imp :  Hardcoded for svg file only. If different file, change this code to dynamic.
        eagle_icon_container_open_button: function (e) {
            var eagle_self = this;
            eagle_self._setValue(eagle_self.ksSelectedIcon);
        },

        eagle_fa_icon_search: function (e) {
            var self = this
            self.$el.find('.eagle_fa_search_icon').remove()
            var eagle_fa_icon_name = self.$el.find('.eagle_modal_icon_input')[0].value
            if (eagle_fa_icon_name.slice(0, 3) === "fa-") {
                eagle_fa_icon_name = eagle_fa_icon_name.slice(3)
            }
            var eagle_fa_icon_render = $('<div>').addClass('eagle_icon_container_list eagle_fa_search_icon')
            $('<span>').attr('id', 'ks.' + eagle_fa_icon_name.toLocaleLowerCase()).addClass("fa fa-" + eagle_fa_icon_name.toLocaleLowerCase() + " fa-4x").appendTo($(eagle_fa_icon_render))
            $(eagle_fa_icon_render).appendTo(self.$el.find('.eagle_icon_container_grid_view'))
        },

        eagle_modal_icon_input_enter: function (e) {
            var eagle_self = this
            if (e.keyCode == 13) {
                eagle_self.$el.find('.eagle_fa_icon_search').click()
            }
        },
    });

    registry.add('eagle_image_widget', KsImageWidget);

    return {
        KsImageWidget: KsImageWidget,
    };
});