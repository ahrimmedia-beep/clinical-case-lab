-- Where one attempt sits among the case's cohort: humans + the simulated cohort.
-- AI players (simulated_label 'ai:%') are benchmarks, never part of the cohort.
-- percent_rank() = (rank - 1) / (n - 1) over (points, right_count): ties share the lower rank.
WITH cohort AS (
    SELECT
        a.id,
        a.is_simulated,
        percent_rank() OVER (ORDER BY a.points, a.right_count) AS pct
    FROM attempts AS a
    WHERE a.case_id = :case_id
      AND coalesce(a.simulated_label, '') NOT LIKE 'ai:%'
)
SELECT
    (SELECT c.pct FROM cohort AS c WHERE c.id = :attempt_id) AS percent_rank,
    count(*) AS cohort_size,
    coalesce(bool_or(cohort.is_simulated), false) AS cohort_is_simulated
FROM cohort
