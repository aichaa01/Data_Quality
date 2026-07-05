

-- Dimension des regles metier de qualite
select * from (values
    ('TX_GAB_SANS_ID',              'Transaction GAB sans identifiant de guichet',      'coherence',  'accepted', 'low'),
    ('TX_NON_GAB_AVEC_ID',          'Transaction non-GAB avec identifiant de guichet',  'coherence',  'accepted', 'medium'),
    ('CARTE_ACTIVE_COMPTE_CLOTURE', 'Carte active associee a un compte cloture',        'coherence',  'rejected', 'high'),
    ('TX_COMPTE_INEXISTANT',        'Transaction referencant un compte absent',         'coherence',  'rejected', 'high'),
    ('CLIENT_AGENCE_FERMEE',        'Client rattache a une agence fermee',              'coherence',  'accepted', 'medium'),
    ('COMPTE_CLIENT_INEXISTANT',    'Compte referencant un client absent',              'coherence',  'rejected', 'high'),
    ('DIGITAL_CLIENT_INEXISTANT',   'Usage digital referencant un client absent',       'coherence',  'rejected', 'high'),
    ('CONTACT_INVALIDE',            'Client sans moyen de contact valide',              'exactitude', 'rejected', 'medium'),
    ('AUCUNE',                      'Enregistrement valide, aucune anomalie',           'aucune',     'accepted', 'low')
) as t(rule_id, description, dimension, decision_recommandee, severite_type)