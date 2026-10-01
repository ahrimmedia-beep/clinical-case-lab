import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Pill } from "@/components/ui/pill";
import { SegmentedBar } from "@/components/ui/segmented-bar";
import { StateIcon } from "@/components/ui/state-icon";

export default function HomePage() {
  return (
    <div className="mx-auto max-w-site px-4 py-24 sm:px-6">
      <Eyebrow>Case Lab</Eyebrow>
      <h1 className="mt-3 text-[clamp(31px,4.2vw,54px)]">Clinical cases, end to end</h1>
      <Card className="mt-10 max-w-[560px]">
        <CardHeader title="Case debrief" tag="Preview" />
        <CardBody className="space-y-3">
          <SegmentedBar label="7 right, 2 wrong, 2 missed" segments={[{ tone: "right", value: 7 }, { tone: "wrong", value: 2 }, { tone: "missed", value: 2 }]} />
          <div className="flex flex-wrap gap-1.5">
            <Pill tone="right"><StateIcon state="right" />7 right</Pill>
            <Pill tone="wrong"><StateIcon state="wrong" />2 wrong</Pill>
            <Pill tone="missed"><StateIcon state="missed" />2 missed</Pill>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
