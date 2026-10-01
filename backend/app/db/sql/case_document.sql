-- The whole case (answer key included) as one jsonb document, in ClinicalCase shape.
-- One round trip, no N+1: every child collection is a correlated jsonb_agg subquery.
-- Server-side only: the public view is projected from it in app/case_views.py.
SELECT
    c.id,
    c.slug,
    c.review_status,
    c.reviewed_at,
    jsonb_build_object(
        'schema_version', c.schema_version,
        'title', c.title,
        'specialty', c.specialty,
        'difficulty', c.difficulty,
        'estimated_minutes', c.estimated_minutes,
        'patient', jsonb_build_object(
            'display_name', c.patient_display_name,
            'age_years', c.patient_age,
            'sex', c.patient_sex
        ),
        'chief_complaint', c.chief_complaint,
        'vignette', c.vignette,
        'findings', coalesce((
            SELECT jsonb_agg(
                jsonb_build_object('category', f.category, 'text', f.text, 'evidence', f.evidence)
                ORDER BY f.position
            )
            FROM case_findings AS f
            WHERE f.case_id = c.id
        ), '[]'::jsonb),
        'measurements', coalesce((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'kind', m.kind, 'name', m.name, 'value', m.value,
                    'value_text', m.value_text, 'unit', m.unit, 'flag', m.flag,
                    'evidence', m.evidence
                )
                ORDER BY m.position
            )
            FROM case_measurements AS m
            WHERE m.case_id = c.id
        ), '[]'::jsonb),
        'final_diagnosis', (
            SELECT jsonb_build_object('name', d.name, 'icd10', d.icd10, 'evidence', d.evidence)
            FROM case_diagnoses AS d
            WHERE d.case_id = c.id AND d.role = 'final'
        ),
        'differential', coalesce((
            SELECT jsonb_agg(
                jsonb_build_object('name', d.name, 'icd10', d.icd10, 'evidence', d.evidence)
                ORDER BY d.position
            )
            FROM case_diagnoses AS d
            WHERE d.case_id = c.id AND d.role = 'differential'
        ), '[]'::jsonb),
        'decisions', coalesce((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'stage', k.stage,
                    'prompt', k.prompt,
                    'explanation', k.explanation,
                    'options', coalesce((
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'key', o.key, 'text', o.text,
                                'is_correct', o.is_correct, 'is_harmful', o.is_harmful,
                                'feedback', o.feedback, 'reveal', o.reveal
                            )
                            ORDER BY o.position
                        )
                        FROM decision_options AS o
                        WHERE o.decision_id = k.id
                    ), '[]'::jsonb),
                    'accepted_answers', coalesce((
                        SELECT jsonb_agg(a.text ORDER BY a.id)
                        FROM decision_accepted_answers AS a
                        WHERE a.decision_id = k.id
                    ), '[]'::jsonb)
                )
                ORDER BY k.id
            )
            FROM case_decisions AS k
            WHERE k.case_id = c.id
        ), '[]'::jsonb),
        'source', jsonb_build_object(
            'kind', c.source_kind,
            'provider', c.source_provider,
            'model', c.source_model,
            'prompt_version', c.prompt_version,
            'text', c.source_text
        )
    ) AS doc
FROM cases AS c
WHERE c.slug = :slug
