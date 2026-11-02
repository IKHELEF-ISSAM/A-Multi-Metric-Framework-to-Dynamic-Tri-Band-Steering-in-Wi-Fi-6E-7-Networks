
import { Box, IconButton, Tooltip } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import { useState } from "react";

import Header from "../../components/Header";
import LineChart from "../../components/LineChart";

const Line = () => {
    const [refreshKey, setRefreshKey] = useState(0);

    const handleRefresh = () => {
        setRefreshKey((prev) => prev + 1);
    };

    return (
        <Box m="20px">
            <Box
                display="flex"
                justifyContent="space-between"
                alignItems="center"
            >
                <Header
                    title="Tri-Bands Line Chart"
               
                />

                <Tooltip title="Refresh graph">
                    <IconButton
                        onClick={handleRefresh}
                        size="large"
                    >
                        <RefreshIcon />
                    </IconButton>
                </Tooltip>
            </Box>

            <Box height="75vh">
                <LineChart key={refreshKey} />
            </Box>
        </Box>
    );
};

export default Line;

