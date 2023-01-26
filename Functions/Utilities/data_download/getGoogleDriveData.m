function getGoogleDriveData(fileName, fileID, filePath)
% PURPOSE: This function downloads a file from Google drive
%------------------------------------------------------------------------------------------
% USAGE:   
% getGoogleDriveData(fileName, fileID, fileStorePath)                                           
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -fileName - name of file to be downloaded
%        -fileID - google drive file ID
%        -filePath - path where the file will be saved
%------------------------------------------------------------------------------------------
% Output:
%------------------------------------------------------------------------------------------
% Examples:
%
% getGoogleDriveData(fileName, fileID, fileStorePath)                                     
%------------------------------------------------------------------------------------------
% Dependencies:
%       Used in getChenZimmermanAnomalies(), 
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.

try
    % Store the URL
    fileURL = sprintf('https://drive.google.com/uc?export=download&id=%s', fileID);
    request = matlab.net.http.RequestMessage();

    % For large file, google drive redirects to an information page about
    % virus scanning. For those, the response will have a confirmation
    % code, which we need to check for
    response = send(request, matlab.net.URI(fileURL));
    responseText = char(response.Body.Data);
    [startIndex, endIndex] = regexpi(responseText, 'confirm=[A-Z]"');

    % If no confirmation code, no need to change the URL
    if isempty(startIndex)
        newURL = fileURL;
    else
        % If there is one, we need to add it to the URL
        confirmCode = responseText(startIndex+8 : endIndex-1);
        newURL = strcat(fileURL, sprintf('&confirm=%s', confirmCode));
    end

    % Download the file
    urlwrite(newURL,[filePath, fileName]);

    % If it's a zip file, we'll unzip it
    if find(regexpi(fileName, '.zip'))
        unzip(fileName, filePath);
    end
    fprintf('File %s with id %s was successfully downloaded from Google drive at %s.\n', fileName, fileID, char(datetime('now')));

catch 
    fprintf('WARNING: The %s file with Google drive id %s was not downloaded from Google drive.\n', fileName, fileID);
end