import { Routes, Route } from "react-router-dom";
import { ColorModeContext, useMode } from "./theme";
import { CssBaseline, ThemeProvider } from "@mui/material";
import Topbar from "./scenes/global/Topbar";
import Sidebar from "./scenes/global/Sidebar";
import Dashboard from "./scenes/dashboard";
import Team from "./scenes/team";
import Contacts from "./scenes/contacts";
import Steering from "./scenes/Steering";
import Configuration from "./scenes/Configuration";
import Calendar from "./scenes/calendar";
import FAQ from "./scenes/faq";
import RSSI from "./scenes/RSSI";
import RSSI2 from "./scenes/RSSI2";
import Throughput from "./scenes/Throughput";
import Bands from "./scenes/Bands";
import Scores from "./scenes/Scores";
import Geography from "./scenes/geography";
import Retransmissions from "./scenes/Retransmissions";

function App() {
  const [theme, colorMode] = useMode();

  return (
    <ColorModeContext.Provider value={colorMode}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <div className="app">
          <Sidebar />
          <main className="content">
            <Topbar />
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/team" element={<Team />} />
              <Route path="/contacts" element={<Contacts />} />
              <Route path="/Steering" element={<Steering />} />
              <Route path="/Configuration" element={<Configuration />} />
              <Route path="/calendar" element={<Calendar />} />
              <Route path="/faq" element={<FAQ />} />
              <Route path="/RSSI" element={<RSSI />} />
                    <Route path="/RSSI2" element={<RSSI2 />} />
              <Route path="/Throughput" element={<Throughput />} />
              <Route path="/Bands" element={<Bands />} />
              <Route path="/Scores" element={<Scores/>} />
              <Route path="/geography" element={<Geography />} />
                <Route path="/Retransmissions" element={<Retransmissions />} />
            </Routes>
          </main>
        </div>
      </ThemeProvider>
    </ColorModeContext.Provider>
  );
}

export default App;
