import { BrowserRouter, Route, Routes } from "react-router-dom";
import { MenuPage } from "./pages/MenuPage";
import { EditorPage } from "./pages/EditorPage";
import { ViewerPage } from "./pages/ViewerPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MenuPage />} />
        <Route path="/dashboards/:id/edit" element={<EditorPage />} />
        <Route path="/dashboards/:id" element={<ViewerPage />} />
      </Routes>
    </BrowserRouter>
  );
}
