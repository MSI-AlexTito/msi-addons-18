# -*- coding: utf-8 -*-
{
    'name': "Development License Bypass",
    'summary': """
        Bypass enterprise license checks in development environment
        """,
    'description': """
        This module bypasses enterprise license warnings in development environments.
        WARNING: Only for development use - do not install in production!
    """,
    'author': "Alex Minjo",
    'version': '18.0.1.0.0',
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
    'category': 'Administration',
    'depends': ['base', 'web_enterprise'],
    
    'assets': {
        'web.assets_backend': [
            'license_enterprise_reminder/static/src/js/enterprise_subscription_service.js',
        ],
    },
}