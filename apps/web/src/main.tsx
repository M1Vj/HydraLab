import { createRoot } from "react-dom/client";
import { WorkbenchRoot } from "./workspace/Workbench";
import "./styles.css";

createRoot(document.getElementById("root")!).render(<WorkbenchRoot />);
