import { Navigate, Route, Routes } from "react-router-dom";
import { useSession } from "./auth/session";
import { ProductShell } from "./components/shell";
import { LoadingState } from "./components/ui";
import { Entry } from "./routes/Entry";
import { RoleHome } from "./routes/RoleHome";
import { PeoplePage } from "./routes/manager/People";
import { GroupsPage } from "./routes/manager/Groups";
import { SchedulePage } from "./routes/manager/Schedule";
import { AttendancePage } from "./routes/manager/Attendance";
import { MoneyPage } from "./routes/manager/Money";
import { CommunicationsPage } from "./routes/manager/Communications";
import { DocumentsPage } from "./routes/manager/Documents";
import { EventsPage } from "./routes/parent/Events";
import { MorePage } from "./routes/More";
import { ParentNotificationsPage } from "./routes/parent/Notifications";

export function App() {
  const { me, activeContext, loading } = useSession();

  if (loading) return <LoadingState label="Učitavanje sesije…" />;
  if (!me) return <Entry />;
  if (!activeContext)
    return (
      <Entry initialMessage="Vaš nalog nema aktivnu ulogu ni u jednoj školi. Osnujte školu ili se prijavite kodom škole." />
    );

  return (
    <ProductShell>
      <Routes>
        <Route path="/" element={<RoleHome />} />
        <Route path="/ljudi" element={<PeoplePage />} />
        <Route path="/grupe" element={<GroupsPage />} />
        <Route path="/raspored" element={<SchedulePage />} />
        <Route path="/raspored/:sessionId/prisustvo" element={<AttendancePage />} />
        <Route path="/finansije" element={<MoneyPage />} />
        <Route path="/komunikacija" element={<CommunicationsPage />} />
        <Route path="/dokumenti" element={<DocumentsPage />} />
        <Route path="/dogadjaji" element={<EventsPage />} />
        <Route path="/obavestenja" element={<ParentNotificationsPage />} />
        <Route path="/vise" element={<MorePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ProductShell>
  );
}
