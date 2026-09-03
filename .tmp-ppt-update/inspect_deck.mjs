import fs from "node:fs/promises";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const input = "C:/Users/madha/Downloads/DRISHTI_RECURSION_EDITION_II.pptx";
const output = "C:/Drishti AI/.tmp-ppt-update/direct-inspect.ndjson";

const presentation = await PresentationFile.importPptx(await FileBlob.load(input));
const snapshot = await presentation.inspect({
  kind: "slide,textbox,shape,image,table,chart,notes,layout",
  include: "id,slide,name,title,text,textPreview,textChars,textLines,bbox,isPlaceholder",
  maxChars: 50000,
});
await fs.writeFile(output, snapshot.ndjson, "utf8");
