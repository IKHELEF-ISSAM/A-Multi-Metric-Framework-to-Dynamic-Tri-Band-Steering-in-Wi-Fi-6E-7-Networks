import { API_BASE_URL } from "../../api";
import { useEffect, useState } from "react";
import {
    Box,
    Typography,
    useTheme,
    Chip,
    Divider,
    Button,
} from "@mui/material";

import { tokens } from "../../theme";
import Header from "../../components/Header";
import LineChart from "../../components/LineChart";
import BarChart from "../../components/BarChart";

const API_URL = API_BASE_URL;

const Dashboard = () => {
    const theme = useTheme();
    const colors = tokens(theme.palette.mode);

    const [rules, setRules] = useState({});
    const [rulesLoading, setRulesLoading] = useState(true);
    const [rulesError, setRulesError] = useState("");

    const loadRules = async () => {
        try {
            setRulesLoading(true);
            setRulesError("");

            const response = await fetch(`${API_URL}/api/device-rules`);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            setRules(data.rules || {});
        } catch (error) {
            console.error("Rules API:", error);
            setRulesError("Unable to load device rules.");
        } finally {
            setRulesLoading(false);
        }
    };

    useEffect(() => {
        loadRules();
    }, []);

    const ruleEntries = Object.entries(rules);

    return (
        <Box m="20px">
        
        
            {/* PAGE TITLE */}
            <Box mb="25px">
                <Typography
                    variant="h2"
                    fontWeight="bold"
                    color={colors.grey[100]}
                    sx={{ mb: "8px" }}
                >
                    SDN Multi-Metric Controller
                </Typography>

                <Typography
                    variant="h5"
                    color={colors.greenAccent[500]}
                    sx={{
                        maxWidth: "2000px",
                        lineHeight: "1.6",
                    }}
                >
                    Intelligent Software-Defined Networking control
                    for multi-radio wireless environments. The controller
                    continuously monitors network performance using multiple
                    metrics such as signal quality, airtime, throughput,
                    client distribution, and network load to support
                    adaptive optimization and improve overall wireless
                    network performance.
                </Typography>
            </Box>


            {/* DEVICE RULES */}
            <Box
                backgroundColor={colors.primary[400]}
                borderRadius="4px"
                p="20px"
                mb="25px"
            >
                <Box
                    display="flex"
                    justifyContent="space-between"
                    alignItems="center"
                    mb="15px"
                >
                    <Box>
                        <Typography
                            variant="h4"
                            fontWeight="600"
                            color={colors.grey[100]}
                        >
                            Device Optimization Rules
                        </Typography>

                        <Typography
                            variant="body2"
                            color={colors.grey[300]}
                        >
                            Per-device wireless optimization configuration
                        </Typography>
                    </Box>

                    <Button
                        variant="contained"
                        onClick={loadRules}
                        disabled={rulesLoading}
                    >
                        {rulesLoading ? "Loading..." : "Refresh"}
                    </Button>
                </Box>

                <Divider sx={{ mb: "15px" }} />

                {rulesError && (
                    <Typography color={colors.redAccent[400]}>
                        {rulesError}
                    </Typography>
                )}

                {!rulesLoading && !rulesError && ruleEntries.length === 0 && (
                    <Typography color={colors.grey[300]}>
                        No device rules configured yet.
                    </Typography>
                )}

                {!rulesLoading && ruleEntries.length > 0 && (
                    <Box
                        display="grid"
                        gridTemplateColumns={{
                            xs: "1fr",
                            md: "repeat(2, 1fr)",
                        }}
                        gap="15px"
                    >
                        {ruleEntries.map(([mac, rule]) => {
                            const enabledBands = Object.entries(
                                rule.bands || {}
                            )
                                .filter(([, enabled]) => enabled)
                                .map(([band]) => band);

                            return (
                                <Box
                                    key={mac}
                                    backgroundColor={colors.primary[500]}
                                    borderRadius="4px"
                                    p="15px"
                                >
                                    <Box
                                        display="flex"
                                        justifyContent="space-between"
                                        alignItems="center"
                                    >
                                        <Typography
                                            variant="h5"
                                            fontWeight="600"
                                            color={colors.grey[100]}
                                        >
                                            {mac}
                                        </Typography>

                                        <Chip
                                            label={
                                                rule.device_type || "Unknown"
                                            }
                                            size="small"
                                        />
                                    </Box>

                                    <Box
                                        display="flex"
                                        gap="8px"
                                        flexWrap="wrap"
                                        mt="12px"
                                    >
                                        <Chip
                                            label={`Priority: ${
                                                rule.priority || "medium"
                                            }`}
                                            size="small"
                                        />

                                        <Chip
                                            label={`Preferred: ${
                                                rule.preferred_band || "N/A"
                                            }`}
                                            size="small"
                                        />

                                        <Chip
                                            label={`Bands: ${
                                                enabledBands.length
                                                    ? enabledBands.join(", ")
                                                    : "None"
                                            }`}
                                            size="small"
                                        />
                                    </Box>

                                    <Divider sx={{ my: "12px" }} />

                                    <Typography
                                        fontWeight="600"
                                        color={colors.greenAccent[400]}
                                    >
                                        Optimization Weights
                                    </Typography>

                                    <Typography variant="body2">
                                        Clients:{" "}
                                        {rule.weights?.clients ?? 0}
                                        {" | "}
                                        RSSI: {rule.weights?.rssi ?? 0}
                                        {" | "}
                                        Airtime: {rule.weights?.airtime ?? 0}
                                    </Typography>

                                    <Typography variant="body2">
                                        Throughput:{" "}
                                        {rule.weights?.throughput ?? 0}
                                        {" | "}
                                        TX Power:{" "}
                                        {rule.weights?.txpower ?? 0}
                                    </Typography>

                                    <Divider sx={{ my: "12px" }} />

                                    <Typography
                                        fontWeight="600"
                                        color={colors.greenAccent[400]}
                                    >
                                        Thresholds
                                    </Typography>

                                    <Typography variant="body2">
                                        2.4 GHz:{" "}
                                        {rule.thresholds?.["2G"]?.min_rssi ??
                                            "N/A"}{" "}
                                        dBm
                                        {" | "}
                                        5 GHz:{" "}
                                        {rule.thresholds?.["5G"]?.min_rssi ??
                                            "N/A"}{" "}
                                        dBm
                                        {" | "}
                                        6 GHz:{" "}
                                        {rule.thresholds?.["6G"]?.min_rssi ??
                                            "N/A"}{" "}
                                        dBm
                                    </Typography>

                                    <Typography variant="body2" mt="5px">
                                        Min throughput:{" "}
                                        {rule.min_throughput_mbps ?? "N/A"} Mbps
                                        {" | "}
                                        Max airtime:{" "}
                                        {rule.max_airtime_percent ?? "N/A"}%
                                    </Typography>

                                    <Typography variant="body2" mt="5px">
                                        Switch threshold:{" "}
                                        {rule.switch_threshold ?? "N/A"}
                                        {" | "}
                                        Cooldown:{" "}
                                        {rule.cooldown ?? "N/A"}s
                                    </Typography>
                                </Box>
                            );
                        })}
                    </Box>
                )}
            </Box>

            {/* DASHBOARD HEADER */}
            <Header
                title="NETWORK ANALYTICS"
                subtitle="Real-time network monitoring and performance visualization"
            />
{/* CHARTS */}
<Box
    display="grid"
    gridTemplateColumns="repeat(12, 1fr)"
    gridAutoRows="400px"
    gap="20px"
    mt="20px"
>
    <Box
        gridColumn="span 12"
        backgroundColor={colors.primary[400]}
        borderRadius="4px"
        p="20px"
    >
        <Typography
            variant="h5"
            fontWeight="600"
            sx={{ mb: "10px" }}
        >
            Network Performance
        </Typography>

        <Box height="330px">
            <LineChart isDashboard={true} />
        </Box>
    </Box>
</Box>
        </Box>
    );
};

export default Dashboard;
