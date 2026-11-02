import { useState } from "react";
import { Sidebar, Menu, MenuItem } from "react-pro-sidebar";
import {
    Box,
    IconButton,
    Typography,
    useTheme,
} from "@mui/material";
import { Link } from "react-router-dom";
import { tokens } from "../../theme";

import AltRouteIcon from "@mui/icons-material/AltRoute";
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import HelpOutlineOutlinedIcon from "@mui/icons-material/HelpOutlineOutlined";
import BarChartOutlinedIcon from "@mui/icons-material/BarChartOutlined";
import PieChartOutlineOutlinedIcon from "@mui/icons-material/PieChartOutlineOutlined";
import TimelineOutlinedIcon from "@mui/icons-material/TimelineOutlined";
import MenuOutlinedIcon from "@mui/icons-material/MenuOutlined";
import MapOutlinedIcon from "@mui/icons-material/MapOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";

const Item = ({
    title,
    to,
    icon,
    selected,
    setSelected,
}) => {
    const theme = useTheme();
    const colors = tokens(theme.palette.mode);

    return (
        <MenuItem
            component={<Link to={to} />}
            active={selected === title}
            style={{
                color: colors.grey[100],
                backgroundColor:
                    selected === title
                        ? colors.primary[400]
                        : "transparent",
            }}
            onClick={() => setSelected(title)}
            icon={icon}
        >
            <Typography>{title}</Typography>
        </MenuItem>
    );
};

const SidebarComponent = () => {
    const theme = useTheme();
    const colors = tokens(theme.palette.mode);

    const [isCollapsed, setIsCollapsed] =
        useState(false);

    const [selected, setSelected] =
        useState("Dashboard");

    return (
        <Box
            sx={{
                height: "100vh",

                "& .ps-sidebar-container": {
                    background:
                        `${colors.primary[400]} !important`,
                },
            }}
        >
            <Sidebar
                collapsed={isCollapsed}
                rootStyles={{
                    border: "none",
                }}
            >
                <Menu
                    menuItemStyles={{
                        button: ({ active }) => ({
                            backgroundColor:
                                "transparent",

                            color: active
                                ? "#6870fa"
                                : colors.grey[100],

                            padding:
                                "5px 35px 5px 20px",
                        }),
                    }}
                >
                    {/* COLLAPSE */}

                    <MenuItem
                        icon={
                            isCollapsed ? (
                                <MenuOutlinedIcon />
                            ) : undefined
                        }
                        onClick={() =>
                            setIsCollapsed(
                                !isCollapsed
                            )
                        }
                        style={{
                            margin:
                                "10px 0 20px 0",
                            color:
                                colors.grey[100],
                            backgroundColor:
                                "transparent",
                            cursor: "pointer",
                        }}
                    >
                        {!isCollapsed && (
                            <Box
                                display="flex"
                                justifyContent="space-between"
                                alignItems="center"
                                ml="15px"
                            >
                                <Typography
                                    variant="h4"
                                    color={
                                        colors.grey[100]
                                    }
                                >
                                    WIFIP-Project
                                </Typography>

                                <IconButton
                                    onClick={() =>
                                        setIsCollapsed(
                                            !isCollapsed
                                        )
                                    }
                                >
                                    <MenuOutlinedIcon />
                                </IconButton>
                            </Box>
                        )}
                    </MenuItem>

                    {/* PROJECT INFO */}

                    {!isCollapsed && (
                        <Box mb="25px">
                            <Box
                                display="flex"
                                justifyContent="center"
                                alignItems="center"
                            >
                                <img
                                    alt="profile-user"
                                    width="150px"
                                    height="170px"
                                    src="src/assets/Logo Telecom SudParis - Endoss IP Paris V Blanc - RVB.png"
                                    style={{
                                        cursor:
                                            "pointer",
                                        borderRadius:
                                            "50%",
                                    }}
                                />
                            </Box>

                            <Box textAlign="center">
                                <Typography
                                    variant="h2"
                                    color={
                                        colors.grey[100]
                                    }
                                    fontWeight="bold"
                                    sx={{
                                        m:
                                            "15px 0 0 0",
                                    }}
                                >
                                    SDN
                                </Typography>

                                <Typography
                                    variant="h5"
                                    color={
                                        colors
                                            .greenAccent[500]
                                    }
                                >
                                    Multi-metric Controller
                                </Typography>
                            </Box>
                        </Box>
                    )}

                    <Box
                        paddingLeft={
                            isCollapsed
                                ? undefined
                                : "10%"
                        }
                    >
                        {/* DASHBOARD */}

                        <Item
                            title="Dashboard"
                            to="/"
                            icon={
                                <HomeOutlinedIcon />
                            }
                            selected={selected}
                            setSelected={
                                setSelected
                            }
                        />

                        {/* CONFIGURATION */}

                        <Typography
                            variant="h6"
                            color={
                                colors.grey[300]
                            }
                            sx={{
                                m:
                                    "15px 0 5px 20px",
                            }}
                        />

                        <Item
                            title="Configuration"
                            to="/Configuration"
                            icon={
                                <SettingsOutlinedIcon />
                            }
                            selected={selected}
                            setSelected={
                                setSelected
                            }
                        />

                        {/* STEERING */}

                        <Typography
                            variant="h6"
                            color={
                                colors.grey[300]
                            }
                            sx={{
                                m:
                                    "15px 0 5px 20px",
                            }}
                        />

                        <Item
                            title="Steering"
                            to="/Steering"
                            icon={
                                <AltRouteIcon />
                            }
                            selected={selected}
                            setSelected={
                                setSelected
                            }
                        />

                       
                        {/* CHARTS */}

                        <Typography
                            variant="h6"
                            color={
                                colors.grey[300]
                            }
                            sx={{
                                m:
                                    "15px 0 5px 20px",
                            }}
                        >
                           Radio Measures
                        </Typography>

                        <Item
                            title="RSSI "
                            to="/RSSI"
                            icon={
                                    <TimelineOutlinedIcon />
                            }
                            selected={selected}
                            setSelected={
                                setSelected
                            }
                        />
                        <Item
                            title="RSSI Export"
                            to="/RSSI2"
                            icon={
                                    <TimelineOutlinedIcon />
                            }
                            selected={selected}
                            setSelected={
                                setSelected
                            }
                        />
                         <Item
                            title="Throughput "
                            to="/Throughput"
                            icon={
                                    <TimelineOutlinedIcon />
                            }
                            selected={selected}
                            setSelected={
                                setSelected
                            }
                        />
               
                        <Item
                            title="Tri-Bands"
                            to="/Bands"
                            icon={
                                <TimelineOutlinedIcon />
                            }
                            selected={selected}
                            setSelected={
                                setSelected
                            }
                        />
                      
                        <Item
                            title="Retransmissions"
                            to="/Retransmissions"
                            icon={
                                    <TimelineOutlinedIcon />
                            }
                            selected={selected}
                            setSelected={
                                setSelected
                            }
                        />  
                                       
                        {/* CHARTS */}

                        <Typography
                            variant="h6"
                            color={
                                colors.grey[300]
                            }
                            sx={{
                                m:
                                    "15px 0 5px 20px",
                            }}
                        >
                           Multi-metric Scores
                        </Typography>

                                                <Item
                            title="Scores"
                            to="/Scores"
                            icon={
                                <TimelineOutlinedIcon />
                            }
                            selected={selected}
                            setSelected={
                                setSelected
                            }
                        />
 {/* HELP */}

                        <Typography
                            variant="h6"
                            color={
                                colors.grey[300]
                            }
                            sx={{
                                m:
                                    "15px 0 5px 20px",
                            }}
                        >
                            Help
                        </Typography>

                        <Item
                            title="FAQ Page"
                            to="/faq"
                            icon={
                                <HelpOutlineOutlinedIcon />
                            }
                            selected={selected}
                            setSelected={
                                setSelected
                            }
                        />


                    </Box>
                </Menu>
            </Sidebar>
        </Box>
    );
};

export default SidebarComponent;
