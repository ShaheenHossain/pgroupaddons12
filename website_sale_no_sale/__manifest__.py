# Copyright 2018 Denis Mudarisov <http://eagle-erp.com>
{
    "name": """Website Price Hide""",
    "summary": """disable all sales and hide all prices, product visible at website""",
    "category": "eCommerce",
    "images": ["images/main.jpg"],
    "version": "12.0.1.0.1",
    "application": True,

    "author": "Eagle ERP, Md. Shaheen Hossain",
    "website": "http://eagle-erp.com",

    "depends": [
        "website_sale",
    ],
    "external_dependencies": {"python": [], "bin": []},
    "data": [
        "templates.xml",
    ],

    "post_load": None,
    "pre_init_hook": None,
    "post_init_hook": None,
    "uninstall_hook": None,

    "auto_install": False,
    "installable": True,
}
