-- "% of peers chose this": share of the cohort (humans + simulated, AI players excluded)
-- that picked each option.
WITH cohort AS (
    SELECT a.id
    FROM attempts AS a
    WHERE a.case_id = :case_id
      AND coalesce(a.simulated_label, '') NOT LIKE 'ai:%'
),
size AS (
    SELECT count(*) AS n FROM cohort
)
SELECT
    d.stage,
    o.key AS option_key,
    CASE WHEN size.n = 0 THEN 0.0
         ELSE count(cohort.id)::float8 / size.n END AS pick_rate
FROM case_decisions AS d
JOIN decision_options AS o ON o.decision_id = d.id
LEFT JOIN attempt_choices AS ac ON ac.option_id = o.id
LEFT JOIN cohort ON cohort.id = ac.attempt_id
CROSS JOIN size
WHERE d.case_id = :case_id
GROUP BY d.stage, o.key, size.n
ORDER BY d.stage, o.key
