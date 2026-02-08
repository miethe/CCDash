import React, { useState } from 'react';
import { Bell, Trash2, Plus, AlertCircle, Save } from 'lucide-react';
import { MOCK_ALERTS } from '../constants';
import { AlertConfig } from '../types';

export const Settings: React.FC = () => {
  const [alerts, setAlerts] = useState<AlertConfig[]>(MOCK_ALERTS);

  const toggleAlert = (id: string) => {
    setAlerts(alerts.map(a => a.id === id ? { ...a, isActive: !a.isActive } : a));
  };

  const deleteAlert = (id: string) => {
    setAlerts(alerts.filter(a => a.id !== id));
  };

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <div>
        <h2 className="text-3xl font-bold text-slate-100">Settings</h2>
        <p className="text-slate-400 mt-2">Manage application preferences and notification rules.</p>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="p-6 border-b border-slate-800 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="bg-indigo-500/10 p-2 rounded-lg text-indigo-400">
              <Bell size={20} />
            </div>
            <div>
              <h3 className="font-semibold text-slate-100">Alert Configuration</h3>
              <p className="text-sm text-slate-400">Define conditions for system notifications.</p>
            </div>
          </div>
          <button className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors">
            <Plus size={16} />
            New Alert
          </button>
        </div>

        <div className="divide-y divide-slate-800">
          {alerts.map((alert) => (
            <div key={alert.id} className="p-6 flex items-center justify-between group hover:bg-slate-800/30 transition-colors">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-1">
                  <h4 className="font-medium text-slate-200">{alert.name}</h4>
                  <span className={`text-[10px] px-2 py-0.5 rounded border ${
                    alert.isActive 
                      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                      : 'bg-slate-800 text-slate-500 border-slate-700'
                  }`}>
                    {alert.isActive ? 'ACTIVE' : 'INACTIVE'}
                  </span>
                </div>
                
                <div className="flex items-center gap-2 text-sm text-slate-400 mt-2">
                  <span className="font-mono text-indigo-400 bg-indigo-500/10 px-1.5 rounded">{alert.scope}</span>
                  <span>if</span>
                  <span className="font-mono text-slate-300">{alert.metric}</span>
                  <span>is</span>
                  <span className="font-bold text-slate-200">{alert.operator} {alert.threshold}</span>
                </div>
              </div>

              <div className="flex items-center gap-4">
                 <div className="flex flex-col items-end gap-1">
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input 
                        type="checkbox" 
                        className="sr-only peer" 
                        checked={alert.isActive}
                        onChange={() => toggleAlert(alert.id)}
                      />
                      <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
                    </label>
                 </div>
                 <button 
                    onClick={() => deleteAlert(alert.id)}
                    className="p-2 text-slate-500 hover:text-rose-500 hover:bg-rose-500/10 rounded-lg transition-colors"
                 >
                    <Trash2 size={18} />
                 </button>
              </div>
            </div>
          ))}
          
          {alerts.length === 0 && (
            <div className="p-8 text-center text-slate-500 flex flex-col items-center">
              <AlertCircle size={32} className="mb-2 opacity-50" />
              <p>No alerts configured.</p>
            </div>
          )}
        </div>
      </div>

       {/* General Settings (Mock) */}
       <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 opacity-60 pointer-events-none">
          <div className="flex justify-between items-center mb-4">
             <h3 className="font-semibold text-slate-100">General Preferences</h3>
             <Save size={18} />
          </div>
          <div className="grid grid-cols-2 gap-4">
              <div>
                 <label className="block text-sm text-slate-400 mb-1">Theme</label>
                 <select className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-sm">
                    <option>Dark (Default)</option>
                    <option>Light</option>
                    <option>System</option>
                 </select>
              </div>
               <div>
                 <label className="block text-sm text-slate-400 mb-1">Local Project Path</label>
                 <input type="text" value="~/dev/ccdash" className="w-full bg-slate-950 border border-slate-700 rounded p-2 text-sm" readOnly />
              </div>
          </div>
       </div>
    </div>
  );
};