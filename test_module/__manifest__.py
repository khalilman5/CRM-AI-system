{
    'name': 'Test Module',
    'version': '19.0.1.0.0',
    'summary': 'Demo custom module with a Test button and dashboard',
    'category': 'Sales/CRM',
    'depends': ['base', 'crm'],
    'data': [
        'security/ir.model.access.csv',
        'data/dashboard_data.xml',
        'views/dashboard_views.xml',
    ],
    'application': False,
    'license': 'LGPL-3',
}
