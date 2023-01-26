function printCombStratsFigure(fid, Results, filePath)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It plots and stores the combination strategies figure. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printCombStratsFigure(fid, Results)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - fid - file ID for writing
%        - Results - structure with results that are used to print the .tex
%                    latex file and .pdf figures
%        - filePath - the file path where the figure is to be stored
%------------------------------------------------------------------------------------------
% Output:
%        - N/A
%------------------------------------------------------------------------------------------
% Examples:
%
% printCombStratsFigure(fid, Results)
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

% Plot & store the figure
Alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
h=figure('Visible','off');
for i=1:size(Results.Fig_CombStrat.yWith, 2)
    subplot(3,2,i);
    ibbots([Results.Fig_CombStrat.yWithout(:,i) Results.Fig_CombStrat.yWith(:,i)], Results.Fig_CombStrat.x);
    if i==1
        legend({'Without new signal','With new signal'}, 'Location','Northwest');
    end
    title(['Panel ', Alphabet(i), ': ', char(Results.Fig_CombStrat.ttl(i))]);
    set(gca,'FontSize',15);
end
set(gcf, 'PaperPositionMode', 'auto');
set(gcf,'units','normalized','outerposition',[0 0 1 1]);
set(gca,'LooseInset',get(gca,'TightInset'));
exportgraphics(h,[filePath, Results.Text.signalChar, '_figureCombStrats.pdf'],'ContentType','vector')    

% Include Figure 7 in the latex document
numCombinationMethods = length(Results.Fig_CombStrat.ttl);
fprintf(fid, ['\\begin{figure}[!htbp]' '\n']);
fprintf(fid, ['\\begin{center}' '\n']);
fprintf(fid, ['\\hspace{-4mm} \\includegraphics[width=1.015\\linewidth,keepaspectratio]{', Results.Text.signalChar, '_figureCombStrats}' '\n']);
fprintf(fid, ['\\end{center}' '\n']);
fprintf(fid, ['\\caption{Combination strategy performance\\\\' '\n']);    
captionText = ['This figure plots the growth of a \\$1 invested in trading strategies that combine ', ...
              'multiple anomalies following \\citet{ChenVelikov2022}. In all panels, the blue solid lines ', ...
              'indicate combination trading strategies ', ...
              'that utilize ', Results.Text.nAnoms, ' anomalies. The red solid lines indicate ', ...
              'combination trading strategies that utilize the ', Results.Text.nAnoms, ' anomalies as ', ...
              'well as ', Results.Text.signalChar, '. '];

% Add the caption
for i = 1:numCombinationMethods
    captionText = [captionText, 'Panel ', Alphabet(i), ' shows results using \"', char(Results.Fig_CombStrat.ttl(i)), '\" ', ...
                 'as the combination method. '];
end   
captionText = [captionText, 'See Section~\\ref{sec:combStrat} for details on the combination methods. '];
fprintf(fid, captionText);
fprintf(fid, ['\\label{fig:combStrat}}' '\n']);
fprintf(fid, ['\\end{figure}' '\n']);
