-- AI players on this case: the latest attempt per label ('ai:<model>').
SELECT DISTINCT ON (a.simulated_label)
    a.simulated_label AS label,
    a.points,
    a.max_points,
    a.diagnosis_correct,
    a.confidence
FROM attempts AS a
WHERE a.case_id = :case_id
  AND a.simulated_label LIKE 'ai:%'
ORDER BY a.simulated_label, a.created_at DESC, a.id DESC
