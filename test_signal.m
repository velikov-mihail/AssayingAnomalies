
clear
clc

restoredefaultpath;                                                        % Start with the default path
fileName    = matlab.desktop.editor.getActiveFilename;                     % Path to the script 
dirSepIndex = strfind(fileName, filesep);                                  % Index of directory separators
fullPath    = fileName(1:dirSepIndex(end));                                % Path to the package
addpath(genpath(fullPath));

% Set the proper path
setAssayPath(fileName);

%% Choose the signal

clear
clc

% Add the form entries
filePrompt  = 'Select file with exported form entries. Hit cancel if you are running your own signal.';
[fileName, filePath] = uigetfile('*.csv', filePrompt); 
if fileName~=0
    % If you have the exported form entry, read the signal info
    signalInfo = getSignalInfo([filePath, fileName]);
else
    % Do this manually
    signalInfo.Authors       = 'Robert Novy-Marx and Mihail Velikov';
    signalInfo.email         = 'velikov@psu.edu';
    signalInfo.PaperTitle    = 'Assaying Anomalies';
    signalInfo.SignalName    = 'Monetary Policy Exposure';
    signalInfo.SignalAcronym = 'MPE';
    signalInfo.fileLink      = 'mpe.csv';
end

% Get the anomalies
[anoms, labelsCZ, anomaly_summary] = getChenZimmermanAnomalies();
labels.short = labelsCZ;
labels.long = anomaly_summary.LongDescription';


% Run the test signals
nTestSignals = length(signalInfo);
for i = 1:nTestSignals
    % Start a log file
    startLogFile([pwd, filesep], ['test_', signalInfo(i).SignalAcronym]);
    
    try    
        % Run the testing protocol
        runTestSignal(signalInfo(i), anoms, labels);
    catch
        fprintf('Signal %s produced an error.\n', signalInfo(i).SignalAcronym);
    end
    % Toggle off the log
    diary off;
end
