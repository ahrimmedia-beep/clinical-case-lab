-- Catalogue cards: approved cases before drafts, newest first within each group.
-- attempts_count counts humans and the simulated cohort; AI players are not attempts by people.
SELECT
    c.id,
    c.slug,
    c.title,
    c.specialty,
    c.difficulty,
    c.estimated_minutes,
    c.patient_display_name,
    c.patient_age,
    c.patient_sex,
    c.chief_complaint,
    c.source_kind,
    c.review_status,
    c.created_at,
    (SELECT count(*) FROM case_decisions AS d WHERE d.case_id = c.id) AS decision_count,
    (
        SELECT count(*)
        FROM attempts AS a
        WHERE a.case_id = c.id AND coalesce(a.simulated_label, '') NOT LIKE 'ai:%'
    ) AS attempts_count
FROM cases AS c
ORDER BY (c.review_status = 'approved') DESC, (c.source_kind = 'manual') DESC, c.created_at DESC, c.id DESC
