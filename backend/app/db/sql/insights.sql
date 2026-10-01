-- ★3 sponsor view of one case, in one round trip: where the cohort goes wrong.
-- Cohort = humans + the simulated cohort; AI players ('ai:%') are benchmarks, never cohort.
--   options    : per option of every multi-select decision, how many in the cohort picked it
--   wrong_dx   : wrong (answered, not correct) diagnoses grouped by a lower-cased alnum key;
--                Python merges the groups further with the scorer's own normalization
--   key_tests  : per correct work-up option, diagnostic accuracy of those who ordered it vs not
WITH target AS (
    SELECT c.id, c.slug, c.title FROM cases AS c WHERE c.slug = :slug
),
cohort AS (
    SELECT a.id, a.is_simulated, a.diagnosis_correct, a.diagnosis_text
    FROM attempts AS a
    JOIN target ON target.id = a.case_id
    WHERE coalesce(a.simulated_label, '') NOT LIKE 'ai:%'
),
size AS (
    SELECT
        count(*) AS n,
        coalesce(bool_or(cohort.is_simulated), false) AS simulated,
        avg(cohort.diagnosis_correct::int)::float8 AS dx_accuracy
    FROM cohort
),
options AS (
    SELECT
        d.stage, o.position, o.key, o.text, o.is_correct, o.is_harmful,
        count(cohort.id) AS picks
    FROM case_decisions AS d
    JOIN target ON target.id = d.case_id
    JOIN decision_options AS o ON o.decision_id = d.id
    LEFT JOIN attempt_choices AS ac ON ac.option_id = o.id
    LEFT JOIN cohort ON cohort.id = ac.attempt_id
    GROUP BY d.stage, o.position, o.key, o.text, o.is_correct, o.is_harmful
),
wrong_dx AS (
    SELECT
        lower(btrim(regexp_replace(cohort.diagnosis_text, '[^[:alnum:]]+', ' ', 'g'))) AS norm,
        mode() WITHIN GROUP (ORDER BY cohort.diagnosis_text) AS text,
        count(*) AS n
    FROM cohort
    WHERE NOT cohort.diagnosis_correct
    GROUP BY 1
),
key_tests AS (
    SELECT
        o.position, o.key, o.text,
        count(ac.attempt_id) AS chose,
        avg(cohort.diagnosis_correct::int) FILTER (WHERE ac.attempt_id IS NOT NULL)::float8
            AS acc_chosen,
        avg(cohort.diagnosis_correct::int) FILTER (WHERE ac.attempt_id IS NULL)::float8
            AS acc_not
    FROM case_decisions AS d
    JOIN target ON target.id = d.case_id
    JOIN decision_options AS o ON o.decision_id = d.id AND o.is_correct
    CROSS JOIN cohort
    LEFT JOIN attempt_choices AS ac ON ac.option_id = o.id AND ac.attempt_id = cohort.id
    WHERE d.stage = 'workup'
    GROUP BY o.position, o.key, o.text
)
SELECT
    target.id,
    target.slug,
    target.title,
    size.n AS cohort_size,
    size.simulated AS cohort_is_simulated,
    size.dx_accuracy,
    coalesce((
        SELECT jsonb_agg(
            jsonb_build_object(
                'stage', o.stage, 'key', o.key, 'text', o.text, 'is_correct', o.is_correct,
                'is_harmful', o.is_harmful, 'picks', o.picks
            )
            ORDER BY o.stage, o.position
        )
        FROM options AS o
    ), '[]'::jsonb) AS options,
    coalesce((
        SELECT jsonb_agg(
            jsonb_build_object('text', w.text, 'count', w.n) ORDER BY w.n DESC, w.text
        )
        FROM wrong_dx AS w
        WHERE w.norm <> ''
    ), '[]'::jsonb) AS wrong_dx,
    coalesce((
        SELECT jsonb_agg(
            jsonb_build_object(
                'key', k.key, 'text', k.text, 'chose', k.chose,
                'acc_chosen', k.acc_chosen, 'acc_not', k.acc_not
            )
            ORDER BY k.position
        )
        FROM key_tests AS k
    ), '[]'::jsonb) AS key_tests
FROM target
CROSS JOIN size
