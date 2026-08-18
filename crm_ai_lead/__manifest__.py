{
    'name': 'CRM AI Lead Assistant',
    'version': '1.0',
    'category': 'Sales/CRM',
    'summary': 'Create leads from a natural-language prompt',
    'depends': ['crm'],
    'data': [
        'security/ir.model.access.csv',
        'views/crm_ai_lead_wizard_views.xml',
        'views/crm_lead_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'crm_ai_lead/static/src/views/*.js',
            'crm_ai_lead/static/src/views/*.xml',
            'crm_ai_lead/static/src/wizard/*.js',
            'crm_ai_lead/static/src/wizard/*.xml',
            'crm_ai_lead/static/src/wizard/*.css',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
