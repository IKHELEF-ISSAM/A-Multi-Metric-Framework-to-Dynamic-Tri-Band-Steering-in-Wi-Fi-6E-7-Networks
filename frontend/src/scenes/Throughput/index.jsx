
import { Box, Button } from "@mui/material";

import Header from "../../components/Header";
import LineChartThroughput from "../../components/LineChart_Throughput";

const Throughput = () => {
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
                    title="THROUGHPUT MONITORING"
                    subtitle="Tri-band steering impact on Wi-Fi throughput"
                />

                <Button
                    variant="contained"
                    color="success"
                    onClick={() => {
                        window.dispatchEvent(
                            new Event("export-throughput-excel")
                        );
                    }}
                >
                    Export Excel
                </Button>
            </Box>

            <Box height="75vh" mt={2}>
                <LineChartThroughput />
            </Box>
        </Box>
    );
};

export default Throughput;

