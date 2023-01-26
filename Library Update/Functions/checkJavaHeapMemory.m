function checkJavaHeapMemory()
% PURPOSE: This function checks whether a user has set the Java Heap Memory
% to the maximum possible, and sets it to the maximum (1/4 * RAM) if it was
% already set to that.
%------------------------------------------------------------------------------------------
% USAGE:   
% checkJavaHeapMemory()              % Checks the Java Heap Memory
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -None
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% checkJavaHeapMemory()
%------------------------------------------------------------------------------------------
% Dependencies:
%       None
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

% Check if PC
if ispc
    % Check the total RAM
    [~, systemview] = memory;
    totalRAM = systemview.PhysicalMemory.Total/(1024^2);

    % Check the Java Heap memory size
    oldMaxHeapSize = com.mathworks.services.Prefs.getIntegerPref('JavaMemHeapMax');  % MB

    % If Java Heap Memory is not set to 1/4 the total RAM, set it and return an
    % prompting the user to restart MATLAB
    if abs((totalRAM/4)-oldMaxHeapSize)>1    
        com.mathworks.services.Prefs.setIntegerPref('JavaMemHeapMax', totalRAM/4); % MB
        errorMessage = ['Java Heap Memory was set to ', ...
                        char(num2str(totalRAM/4)), ' MB.', ...
                        'Please restart MATLAB and run setup_library.m again\n\n'];
        error(errorMessage);
    end
elseif isunix
    fprintf(['Java Heap Memory check cannot be run on UNIX/LINUX systems. ', ...
            'Java Heap Memory needs to be set to maximum available.\n\n\n']);
elseif ismac
    fprintf(['Java Heap Memory check cannot be run on Mac systems. ', ...
            'Java Heap Memory needs to be set to maximum available.\n\n\n']);        
end