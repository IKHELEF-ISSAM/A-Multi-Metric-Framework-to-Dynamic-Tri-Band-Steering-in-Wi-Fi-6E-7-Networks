import { Box, IconButton, Tooltip, Button } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import FileDownloadIcon from "@mui/icons-material/FileDownload";
import { useState } from "react";

import Header from "../../components/Header";
import LineChart from "../../components/LineChart_rssi_old";

const Line = () => {
    const [refreshKey, setRefreshKey] = useState(0);
    const [exportFunction, setExportFunction] = useState(null);

    const handleRefresh = () => {
        setRefreshKey((prev) => prev + 1);
        setExportFunction(null);
    };

    return (
        <Box m="20px">
            <Box
                display="flex"
                justifyContent="space-between"
                alignItems="center"
                flexWrap="wrap"
                gap={2}
            >
                <Header
                    title="RSSI Monitoring"
                    subtitle="Tri-band steering impact on Wi-Fi clients"
                />

                <Box display="flex" alignItems="center" gap={1}>

                    <Tooltip title="Refresh graph">
                        <IconButton
                            onClick={handleRefresh}
                            size="large"
                        >
                            <RefreshIcon />
                        </IconButton>
                    </Tooltip>
                </Box>
            </Box>

            <Box height="75vh">
                <LineChart
                    key={refreshKey}
                    onExportReady={setExportFunction}
                />
            </Box>
        </Box>
    );
};

export default Line;
