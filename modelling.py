import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.express as px
from scipy.optimize import fsolve, minimize
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import json
import os
from datetime import datetime
import subprocess
import sys
hdhadhksdadsd
class ThermodynamicProperties:
    def __init__(self, fluid_type='water'):
        self.fluid_type = fluid_type
        self.R_universal = 8.314
        self.fluid_properties = {
            'water': {'R': 0.4615, 'cp': 1.872, 'cv': 1.410, 'gamma': 1.327, 'M': 18.015},
            'air': {'R': 0.287, 'cp': 1.005, 'cv': 0.718, 'gamma': 1.4, 'M': 28.97},
            'r134a': {'R': 0.0815, 'cp': 0.852, 'cv': 0.770, 'gamma': 1.106, 'M': 102.03}
        }
        
    def get_property(self, prop_name):
        if self.fluid_type in self.fluid_properties:
            return self.fluid_properties[self.fluid_type].get(prop_name, 0)
        return 0
    
    def ideal_gas_enthalpy(self, T):
        cp = self.get_property('cp')
        return cp * T * 1000
    
    def ideal_gas_entropy(self, T, P, T_ref=298.15, P_ref=101325):
        cp = self.get_property('cp')
        R = self.get_property('R')
        return cp * np.log(T/T_ref) - R * np.log(P/P_ref)
    
    def calculate_exergy(self, h, s, h_ref, s_ref, T_ref):
        return (h - h_ref) - T_ref * (s - s_ref)

class StatePoint:
    def __init__(self, state_id, name=""):
        self.id = state_id
        self.name = name
        self.T = 0.0
        self.P = 0.0
        self.h = 0.0
        self.s = 0.0
        self.exergy = 0.0
        self.density = 0.0
        self.quality = -1
        self.mass_flow = 1.0
        
    def set_properties(self, T=None, P=None, h=None, s=None):
        if T is not None:
            self.T = T
        if P is not None:
            self.P = P
        if h is not None:
            self.h = h
        if s is not None:
            self.s = s
            
    def calculate_ideal_properties(self, thermo_props, T_ref, P_ref):
        self.h = thermo_props.ideal_gas_enthalpy(self.T)
        self.s = thermo_props.ideal_gas_entropy(self.T, self.P, T_ref, P_ref)
        
    def calculate_exergy_value(self, h_ref, s_ref, T_ref):
        self.exergy = (self.h - h_ref) - T_ref * (self.s - s_ref)
        return self.exergy
    
    def to_dict(self):
        return {
            'State': self.id,
            'Name': self.name,
            'Temperature': self.T,
            'Pressure': self.P,
            'Enthalpy': self.h,
            'Entropy': self.s,
            'Exergy': self.exergy,
            'Quality': self.quality,
            'MassFlow': self.mass_flow
        }

class RankineCycleAnalyzer:
    def __init__(self, p_high, p_low, t_inlet, efficiency, mass_flow=1.0):
        self.p_high = p_high * 1e6
        self.p_low = p_low * 1e3
        self.t_inlet = t_inlet + 273.15
        self.efficiency = efficiency
        self.mass_flow = mass_flow
        self.states = []
        self.T_ref = 298.15
        self.P_ref = 101325
        self.thermo = ThermodynamicProperties('water')
        
    def calculate_cycle(self):
        s1 = StatePoint(1, "Turbine Inlet")
        s1.T = self.t_inlet
        s1.P = self.p_high
        s1.calculate_ideal_properties(self.thermo, self.T_ref, self.P_ref)
        
        s2 = StatePoint(2, "Turbine Outlet")
        s2.P = self.p_low
        h1 = s1.h
        s_ideal = s1.s
        h2_ideal = h1 - 0.85 * (self.p_high - self.p_low) / 1000
        s2.h = h1 - self.efficiency * (h1 - h2_ideal)
        s2.T = s2.h / self.thermo.get_property('cp') / 1000
        s2.s = self.thermo.ideal_gas_entropy(s2.T, s2.P, self.T_ref, self.P_ref)
        
        s3 = StatePoint(3, "Condenser Outlet")
        s3.P = self.p_low
        s3.T = 320
        s3.calculate_ideal_properties(self.thermo, self.T_ref, self.P_ref)
        s3.quality = 0
        
        s4 = StatePoint(4, "Pump Outlet")
        s4.P = self.p_high
        h3 = s3.h
        h4_ideal = h3 + (self.p_high - self.p_low) / 1000
        s4.h = h3 + (h4_ideal - h3) / self.efficiency
        s4.T = s4.h / self.thermo.get_property('cp') / 1000
        s4.s = self.thermo.ideal_gas_entropy(s4.T, s4.P, self.T_ref, self.P_ref)
        
        h_ref = self.thermo.ideal_gas_enthalpy(self.T_ref)
        s_ref = self.thermo.ideal_gas_entropy(self.T_ref, self.P_ref, self.T_ref, self.P_ref)
        
        for state in [s1, s2, s3, s4]:
            state.calculate_exergy_value(h_ref, s_ref, self.T_ref)
            state.mass_flow = self.mass_flow
            
        self.states = [s1, s2, s3, s4]
        return self.states
    
    def calculate_performance(self):
        if len(self.states) < 4:
            self.calculate_cycle()
        
        s1, s2, s3, s4 = self.states
        
        w_turbine = self.mass_flow * (s1.h - s2.h)
        w_pump = self.mass_flow * (s4.h - s3.h)
        q_in = self.mass_flow * (s1.h - s4.h)
        q_out = self.mass_flow * (s2.h - s3.h)
        
        w_net = w_turbine - w_pump
        thermal_eff = w_net / q_in if q_in > 0 else 0
        
        heat_rate = 3600 / thermal_eff if thermal_eff > 0 else 0
        
        exergy_destroyed_turbine = self.mass_flow * self.T_ref * (s2.s - s1.s)
        exergy_destroyed_pump = self.mass_flow * self.T_ref * (s4.s - s3.s)
        exergy_destroyed_boiler = self.mass_flow * self.T_ref * (s1.s - s4.s - q_in / s1.T)
        exergy_destroyed_condenser = self.mass_flow * self.T_ref * (s3.s - s2.s + q_out / s3.T)
        
        total_exergy_destroyed = (exergy_destroyed_turbine + exergy_destroyed_pump + 
                                  exergy_destroyed_boiler + exergy_destroyed_condenser)
        
        exergy_efficiency = 1 - total_exergy_destroyed / (self.mass_flow * (s1.exergy - s3.exergy))
        
        return {
            'turbine_work': w_turbine,
            'pump_work': w_pump,
            'net_work': w_net,
            'heat_input': q_in,
            'heat_output': q_out,
            'thermal_efficiency': thermal_eff * 100,
            'heat_rate': heat_rate,
            'exergy_destroyed_turbine': exergy_destroyed_turbine,
            'exergy_destroyed_pump': exergy_destroyed_pump,
            'exergy_destroyed_boiler': exergy_destroyed_boiler,
            'exergy_destroyed_condenser': exergy_destroyed_condenser,
            'total_exergy_destroyed': total_exergy_destroyed,
            'exergy_efficiency': exergy_efficiency * 100
        }

class BraytonCycleAnalyzer:
    def __init__(self, pressure_ratio, t_max, t_min=298.15, efficiency=0.85, mass_flow=1.0):
        self.pressure_ratio = pressure_ratio
        self.t_max = t_max
        self.t_min = t_min
        self.efficiency = efficiency
        self.mass_flow = mass_flow
        self.states = []
        self.T_ref = 298.15
        self.P_ref = 101325
        self.thermo = ThermodynamicProperties('air')
        
    def calculate_cycle(self):
        gamma = self.thermo.get_property('gamma')
        
        s1 = StatePoint(1, "Compressor Inlet")
        s1.T = self.t_min
        s1.P = self.P_ref
        s1.calculate_ideal_properties(self.thermo, self.T_ref, self.P_ref)
        
        s2 = StatePoint(2, "Compressor Outlet")
        s2.P = self.P_ref * self.pressure_ratio
        T2_ideal = s1.T * (self.pressure_ratio ** ((gamma - 1) / gamma))
        s2.T = s1.T + (T2_ideal - s1.T) / self.efficiency
        s2.calculate_ideal_properties(self.thermo, self.T_ref, self.P_ref)
        
        s3 = StatePoint(3, "Turbine Inlet")
        s3.T = self.t_max
        s3.P = s2.P
        s3.calculate_ideal_properties(self.thermo, self.T_ref, self.P_ref)
        
        s4 = StatePoint(4, "Turbine Outlet")
        s4.P = self.P_ref
        T4_ideal = s3.T / (self.pressure_ratio ** ((gamma - 1) / gamma))
        s4.T = s3.T - self.efficiency * (s3.T - T4_ideal)
        s4.calculate_ideal_properties(self.thermo, self.T_ref, self.P_ref)
        
        h_ref = self.thermo.ideal_gas_enthalpy(self.T_ref)
        s_ref = self.thermo.ideal_gas_entropy(self.T_ref, self.P_ref, self.T_ref, self.P_ref)
        
        for state in [s1, s2, s3, s4]:
            state.calculate_exergy_value(h_ref, s_ref, self.T_ref)
            state.mass_flow = self.mass_flow
            
        self.states = [s1, s2, s3, s4]
        return self.states
    
    def calculate_performance(self):
        if len(self.states) < 4:
            self.calculate_cycle()
        
        s1, s2, s3, s4 = self.states
        
        w_compressor = self.mass_flow * (s2.h - s1.h)
        w_turbine = self.mass_flow * (s3.h - s4.h)
        q_in = self.mass_flow * (s3.h - s2.h)
        q_out = self.mass_flow * (s4.h - s1.h)
        
        w_net = w_turbine - w_compressor
        thermal_eff = w_net / q_in if q_in > 0 else 0
        
        bwr = w_compressor / w_turbine if w_turbine > 0 else 0
        
        exergy_destroyed_compressor = self.mass_flow * self.T_ref * (s2.s - s1.s)
        exergy_destroyed_turbine = self.mass_flow * self.T_ref * (s4.s - s3.s)
        exergy_destroyed_combustor = self.mass_flow * self.T_ref * (s3.s - s2.s - q_in / s3.T)
        
        total_exergy_destroyed = (exergy_destroyed_compressor + exergy_destroyed_turbine + 
                                  exergy_destroyed_combustor)
        
        return {
            'compressor_work': w_compressor,
            'turbine_work': w_turbine,
            'net_work': w_net,
            'heat_input': q_in,
            'heat_output': q_out,
            'thermal_efficiency': thermal_eff * 100,
            'back_work_ratio': bwr * 100,
            'exergy_destroyed_compressor': exergy_destroyed_compressor,
            'exergy_destroyed_turbine': exergy_destroyed_turbine,
            'exergy_destroyed_combustor': exergy_destroyed_combustor,
            'total_exergy_destroyed': total_exergy_destroyed
        }

class DataManager:
    def __init__(self):
        self.current_data = None
        self.history = []
        
    def load_from_cpp(self, filename='cycle_data.csv'):
        try:
            df = pd.read_csv(filename)
            self.current_data = df
            return df
        except FileNotFoundError:
            messagebox.showerror("Error", f"{filename} not found!")
            return None
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load data: {str(e)}")
            return None
    
    def save_cycle_data(self, states, filename='python_cycle_data.csv'):
        data = [state.to_dict() for state in states]
        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)
        self.current_data = df
        return df
    
    def export_to_json(self, data, filename='cycle_results.json'):
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
    
    def save_performance_report(self, performance_data, filename='performance_report.txt'):
        with open(filename, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("THERMODYNAMIC CYCLE PERFORMANCE REPORT\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for key, value in performance_data.items():
                formatted_key = key.replace('_', ' ').title()
                if isinstance(value, float):
                    f.write(f"{formatted_key}: {value:.4f}\n")
                else:
                    f.write(f"{formatted_key}: {value}\n")

class VisualizationEngine:
    def __init__(self):
        self.fig = None
        
    def plot_ts_diagram(self, states, title="Temperature-Entropy Diagram"):
        temperatures = [state.T for state in states]
        entropies = [state.s for state in states]
        state_names = [f"State {state.id}" for state in states]
        
        temperatures.append(states[0].T)
        entropies.append(states[0].s)
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=entropies,
            y=temperatures,
            mode='lines+markers',
            name='Cycle',
            line=dict(color='blue', width=2),
            marker=dict(size=10, color='red')
        ))
        
        for i, state in enumerate(states):
            fig.add_annotation(
                x=state.s,
                y=state.T,
                text=state_names[i],
                showarrow=True,
                arrowhead=2,
                ax=20,
                ay=-30
            )
        
        fig.update_layout(
            title=title,
            xaxis_title='Entropy (kJ/kg·K)',
            yaxis_title='Temperature (K)',
            hovermode='closest',
            showlegend=True,
            width=900,
            height=600
        )
        
        self.fig = fig
        return fig
    
    def plot_ph_diagram(self, states, title="Pressure-Enthalpy Diagram"):
        pressures = [state.P / 1e6 for state in states]
        enthalpies = [state.h / 1000 for state in states]
        state_names = [f"State {state.id}" for state in states]
        
        pressures.append(states[0].P / 1e6)
        enthalpies.append(states[0].h / 1000)
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=enthalpies,
            y=pressures,
            mode='lines+markers',
            name='Cycle',
            line=dict(color='green', width=2),
            marker=dict(size=10, color='orange')
        ))
        
        for i, state in enumerate(states):
            fig.add_annotation(
                x=state.h / 1000,
                y=state.P / 1e6,
                text=state_names[i],
                showarrow=True,
                arrowhead=2,
                ax=20,
                ay=-30
            )
        
        fig.update_layout(
            title=title,
            xaxis_title='Enthalpy (MJ/kg)',
            yaxis_title='Pressure (MPa)',
            hovermode='closest',
            showlegend=True,
            width=900,
            height=600
        )
        
        return fig
    
    def plot_sankey_exergy(self, states, performance_data, cycle_type='Rankine'):
        if cycle_type == 'Rankine':
            labels = ['Boiler Input', 'Turbine', 'Condenser', 'Pump', 
                     'Net Work Output', 'Exergy Loss']
            
            exergy_in = states[0].exergy * states[0].mass_flow
            exergy_turbine = performance_data.get('exergy_destroyed_turbine', 0)
            exergy_condenser = performance_data.get('exergy_destroyed_condenser', 0)
            exergy_pump = performance_data.get('exergy_destroyed_pump', 0)
            exergy_boiler = performance_data.get('exergy_destroyed_boiler', 0)
            
            source = [0, 1, 1, 2, 3]
            target = [1, 2, 4, 3, 5]
            value = [exergy_in, exergy_turbine, 
                    performance_data.get('net_work', 0),
                    exergy_condenser, exergy_pump]
        else:
            labels = ['Combustor Input', 'Turbine', 'Compressor', 
                     'Net Work Output', 'Exergy Loss']
            
            source = [0, 1, 1, 2]
            target = [1, 2, 3, 4]
            value = [100, 40, 30, 30]
        
        fig = go.Figure(data=[go.Sankey(
            node=dict(
                pad=15,
                thickness=20,
                line=dict(color='black', width=0.5),
                label=labels,
                color=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
            ),
            link=dict(
                source=source,
                target=target,
                value=value,
                color='rgba(0,0,255,0.2)'
            )
        )])
        
        fig.update_layout(
            title=f"Exergy Flow Diagram - {cycle_type} Cycle",
            font=dict(size=12),
            width=1000,
            height=600
        )
        
        return fig
    
    def plot_bar_comparison(self, performance_data):
        components = []
        exergy_values = []
        
        for key, value in performance_data.items():
            if 'exergy_destroyed' in key and 'total' not in key:
                component_name = key.replace('exergy_destroyed_', '').replace('_', ' ').title()
                components.append(component_name)
                exergy_values.append(value)
        
        fig = go.Figure(data=[
            go.Bar(
                x=components,
                y=exergy_values,
                marker_color=['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A']
            )
        ])
        
        fig.update_layout(
            title='Exergy Destruction by Component',
            xaxis_title='Component',
            yaxis_title='Exergy Destroyed (kW)',
            showlegend=False,
            width=800,
            height=500
        )
        
        return fig

class OptimizationEngine:
    def __init__(self):
        self.best_efficiency = 0
        self.best_parameters = {}
        
    def optimize_rankine_pressure(self, t_inlet, p_low, efficiency, mass_flow=1.0):
        def objective(p_high):
            try:
                analyzer = RankineCycleAnalyzer(p_high[0], p_low, t_inlet, efficiency, mass_flow)
                analyzer.calculate_cycle()
                perf = analyzer.calculate_performance()
                return -perf['thermal_efficiency']
            except:
                return 1e10
        
        result = minimize(objective, x0=[10.0], bounds=[(1.0, 30.0)], method='L-BFGS-B')
        
        optimal_p_high = result.x[0]
        analyzer = RankineCycleAnalyzer(optimal_p_high, p_low, t_inlet, efficiency, mass_flow)
        analyzer.calculate_cycle()
        optimal_performance = analyzer.calculate_performance()
        
        return {
            'optimal_high_pressure': optimal_p_high,
            'thermal_efficiency': optimal_performance['thermal_efficiency'],
            'net_work': optimal_performance['net_work'],
            'states': analyzer.states
        }
    
    def optimize_brayton_pressure_ratio(self, t_max, t_min, efficiency, mass_flow=1.0):
        def objective(pr):
            try:
                analyzer = BraytonCycleAnalyzer(pr[0], t_max, t_min, efficiency, mass_flow)
                analyzer.calculate_cycle()
                perf = analyzer.calculate_performance()
                return -perf['thermal_efficiency']
            except:
                return 1e10
        
        result = minimize(objective, x0=[8.0], bounds=[(2.0, 25.0)], method='L-BFGS-B')
        
        optimal_pr = result.x[0]
        analyzer = BraytonCycleAnalyzer(optimal_pr, t_max, t_min, efficiency, mass_flow)
        analyzer.calculate_cycle()
        optimal_performance = analyzer.calculate_performance()
        
        return {
            'optimal_pressure_ratio': optimal_pr,
            'thermal_efficiency': optimal_performance['thermal_efficiency'],
            'net_work': optimal_performance['net_work'],
            'states': analyzer.states
        }

class ThermoOptimizerGUI:
    def __init__(self, master):
        self.master = master
        master.title("Thermodynamic Cycle Optimization Suite v2.0")
        master.geometry("1200x800")
        
        self.data_manager = DataManager()
        self.viz_engine = VisualizationEngine()
        self.opt_engine = OptimizationEngine()
        
        self.create_widgets()
        
    def create_widgets(self):
        notebook = ttk.Notebook(self.master)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.tab_rankine = ttk.Frame(notebook)
        self.tab_brayton = ttk.Frame(notebook)
        self.tab_visualization = ttk.Frame(notebook)
        self.tab_optimization = ttk.Frame(notebook)
        self.tab_cpp_interface = ttk.Frame(notebook)
        
        notebook.add(self.tab_rankine, text='Rankine Cycle')
        notebook.add(self.tab_brayton, text='Brayton Cycle')
        notebook.add(self.tab_visualization, text='Visualization')
        notebook.add(self.tab_optimization, text='Optimization')
        notebook.add(self.tab_cpp_interface, text='C++ Interface')
        
        self.setup_rankine_tab()
        self.setup_brayton_tab()
        self.setup_visualization_tab()
        self.setup_optimization_tab()
        self.setup_cpp_interface_tab()
        
    def setup_rankine_tab(self):
        input_frame = ttk.LabelFrame(self.tab_rankine, text="Input Parameters", padding=10)
        input_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(input_frame, text="High Pressure (MPa):").grid(row=0, column=0, sticky='w', pady=5)
        self.rankine_p_high = ttk.Entry(input_frame, width=15)
        self.rankine_p_high.grid(row=0, column=1, pady=5)
        self.rankine_p_high.insert(0, "10.0")
        
        ttk.Label(input_frame, text="Low Pressure (kPa):").grid(row=1, column=0, sticky='w', pady=5)
        self.rankine_p_low = ttk.Entry(input_frame, width=15)
        self.rankine_p_low.grid(row=1, column=1, pady=5)
        self.rankine_p_low.insert(0, "10.0")
        
        ttk.Label(input_frame, text="Turbine Inlet Temp (°C):").grid(row=2, column=0, sticky='w', pady=5)
        self.rankine_t_inlet = ttk.Entry(input_frame, width=15)
        self.rankine_t_inlet.grid(row=2, column=1, pady=5)
        self.rankine_t_inlet.insert(0, "500")
        
        ttk.Label(input_frame, text="Isentropic Efficiency:").grid(row=3, column=0, sticky='w', pady=5)
        self.rankine_eff = ttk.Entry(input_frame, width=15)
        self.rankine_eff.grid(row=3, column=1, pady=5)
        self.rankine_eff.insert(0, "0.85")
        
        ttk.Label(input_frame, text="Mass Flow (kg/s):").grid(row=4, column=0, sticky='w', pady=5)
        self.rankine_mass_flow = ttk.Entry(input_frame, width=15)
        self.rankine_mass_flow.grid(row=4, column=1, pady=5)
        self.rankine_mass_flow.insert(0, "100")
        
        btn_frame = ttk.Frame(self.tab_rankine)
        btn_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(btn_frame, text="Calculate Cycle", command=self.calculate_rankine).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Export Results", command=self.export_rankine_results).pack(side='left', padx=5)
        
        self.rankine_results = scrolledtext.ScrolledText(self.tab_rankine, height=20, width=80)
        self.rankine_results.pack(fill='both', expand=True, padx=10, pady=10)
        
    def setup_brayton_tab(self):
        input_frame = ttk.LabelFrame(self.tab_brayton, text="Input Parameters", padding=10)
        input_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(input_frame, text="Pressure Ratio:").grid(row=0, column=0, sticky='w', pady=5)
        self.brayton_pr = ttk.Entry(input_frame, width=15)
        self.brayton_pr.grid(row=0, column=1, pady=5)
        self.brayton_pr.insert(0, "8.0")
        
        ttk.Label(input_frame, text="Max Temperature (K):").grid(row=1, column=0, sticky='w', pady=5)
        self.brayton_t_max = ttk.Entry(input_frame, width=15)
        self.brayton_t_max.grid(row=1, column=1, pady=5)
        self.brayton_t_max.insert(0, "1400")
        
        ttk.Label(input_frame, text="Min Temperature (K):").grid(row=2, column=0, sticky='w', pady=5)
        self.brayton_t_min = ttk.Entry(input_frame, width=15)
        self.brayton_t_min.grid(row=2, column=1, pady=5)
        self.brayton_t_min.insert(0, "298.15")
        
        ttk.Label(input_frame, text="Isentropic Efficiency:").grid(row=3, column=0, sticky='w', pady=5)
        self.brayton_eff = ttk.Entry(input_frame, width=15)
        self.brayton_eff.grid(row=3, column=1, pady=5)
        self.brayton_eff.insert(0, "0.85")
        
        ttk.Label(input_frame, text="Mass Flow (kg/s):").grid(
