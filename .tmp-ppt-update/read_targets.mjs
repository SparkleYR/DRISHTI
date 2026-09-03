import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const input = "C:/Users/madha/Downloads/DRISHTI_RECURSION_EDITION_II.pptx";
const ids = [
  "sh/qtk3mx07", "sh/1cbmtor6", "sh/a9sj29gv", "sh/qtgjyhsf",
  "sh/al4n2h0z", "sh/9wnulkby", "sh/2h072143", "sh/8325kje9",
  "sh/1kzydsna", "tb/o7mhsv6t", "sh/zap4nyx4"
];
const presentation = await PresentationFile.importPptx(await FileBlob.load(input));
for (const id of ids) {
  const item = presentation.resolve(id);
  console.log(`ID ${id}`);
  console.log(JSON.stringify(item.text?.toJSON?.() ?? item.text ?? item.preview ?? "[no text]"));
}
