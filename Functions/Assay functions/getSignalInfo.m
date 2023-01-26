function signalInfo = getSignalInfo(fileName)
% PURPOSE: Creates a structure with information from the form submitted to
% the web-app
%------------------------------------------------------------------------------------------
% USAGE: 
%       signalInfo = getSignalInfo(fileName)    
%------------------------------------------------------------------------------------------
% Required Inputs:
%       -fileName - a character array with name of file with exported
%       web-app form entry
%------------------------------------------------------------------------------------------
% Output:
%        -signalInfo - a structure containing information about signal from
%                       the website form
%             -signalInfo.Authors - author(s) name(s)
%             -signalInfo.email - corresponding author email address
%             -signalInfo.PaperTitle - paper title
%             -signalInfo.SignalName - signal name
%             -signalInfo.SignalAcronym - signal acronym
%             -signalInfo.fileLink - link to submitted .csv file
%------------------------------------------------------------------------------------------
% Examples: 
%       fileName = 'mpe_form_entry.csv';
%       signalInfo = getSignalInfo(fileName)    
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Read the file with the signal info
opts = detectImportOptions(fileName);
data = readtable(fileName, opts);
data.Properties.VariableNames(1:6) = {'authors','email','title','signalName','signalAcronym','fileLink'};

nRows = height(data);
for i=1:nRows
    signalInfo(i,1).Authors       = char(data.authors(i));
    signalInfo(i,1).email         = char(data.email(i));
    signalInfo(i,1).PaperTitle    = char(data.title(i));
    signalInfo(i,1).SignalName    = char(data.signalName(i));
    signalInfo(i,1).SignalAcronym = erase(char(data.signalAcronym(i)), ' ');
    signalInfo(i,1).fileLink      = char(data.fileLink(i));
end
