# -*- coding: utf-8 -*-
{
    'name': 'Chilean EDI Debug Logger',
    'version': '1.0',
    'category': 'Accounting/Localizations',
    'summary': 'Debug logger for Chilean SII integration',
    'description': """
Debug Logger for Chilean SII Integration
=========================================
This module adds extensive logging to Chilean EDI operations to debug
differences between environments (odoo.sh vs local).

Logs captured:
- HTTP headers and URLs
- Request/response parameters
- XML content sent/received
- Certificates and tokens
- Timing information
- Server responses
    """,
    'depends': ['l10n_cl_edi'],
    'data': [],
    'auto_install': False,
    'license': 'OEEL-1',
}
