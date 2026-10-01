export type StudioSample = { id: string; label: string; text: string };

/** Synthetic notes written for this repo (no real patients). The fake identifiers show the masking step. */
export const STUDIO_SAMPLES: StudioSample[] = [
  {
    id: "pe",
    label: "Breathless after a flight",
    text:
      "ED note, 03/14/2026. Ms. Jane Doe is a 34-year-old woman with sudden shortness of breath and sharp right-sided chest pain that worsens on inspiration. She returned yesterday from a 14-hour flight. She takes a combined oral contraceptive. She denies fever or cough. On examination: heart rate 112, blood pressure 124/78, SpO2 91% on room air. The left calf is swollen and tender. Labs: D-dimer 2.4 mg/L FEU. CT pulmonary angiography shows a filling defect in the right lower lobe pulmonary artery. Impression: acute pulmonary embolism. Callback number 555-201-3344.",
  },
  {
    id: "ptx",
    label: "Sudden pain at a desk",
    text:
      "Clinic letter. Mr. Tom Hale, MRN 4471923, a 22-year-old tall, thin man who smokes ten cigarettes a day, felt a sudden sharp left-sided chest pain while sitting at his desk, followed by breathlessness. He has no history of trauma and denies fever. Examination: respiratory rate 24, heart rate 104, SpO2 94% on room air, reduced breath sounds and hyper-resonance over the left hemithorax; trachea central. Chest X-ray shows a 3 cm left apical rim of air with a visible pleural edge and no mediastinal shift. Assessment: primary spontaneous pneumothorax. Seen 2026-09-30.",
  },
  {
    id: "lam",
    label: "Cysts on CT (rare)",
    text:
      "Pulmonology referral, 09/02/2026. Dr. Anna Weiss writes about Ms. Laura King, 38, a non-smoker with progressive exertional dyspnoea over two years and two previous right-sided pneumothoraces. She also had a renal angiomyolipoma removed in 2021. She denies cough or joint pain. Spirometry: FEV1/FVC 0.62 with a DLCO of 48% predicted. High-resolution CT shows numerous thin-walled round cysts evenly distributed through both lungs, with normal intervening parenchyma. Serum VEGF-D is 1,240 pg/mL (raised). Working diagnosis: lymphangioleiomyomatosis (LAM). Contact: laura.king@example.com.",
  },
];
