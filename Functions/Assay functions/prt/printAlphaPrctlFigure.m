function printAlphaPrctlFigure(fid, Results, filePath)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It plots and stores the alpha percentiles figure. 
%------------------------------------------------------------------------------------------
% USAGE:   
% printAlphaPrctlFigure(fid, Results)
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
% printAlphaPrctlFigure(fid, Results)
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

% Plot Panel A: Gross
h=figure('Visible','off');
set(gcf,'units','normalized','outerposition',[0 0 1 1]);
orient(gcf,'landscape')
pbaspect([1 1 1])
set(gca,'LooseInset',get(gca,'TightInset'))

subplot(1,2,1);
for i=1:size(Results.Fig_AlphaPrctl.PanelA.y,2)
    plot(Results.Fig_AlphaPrctl.PanelA.x, Results.Fig_AlphaPrctl.PanelA.y(:,i),'LineWidth',4.5,'color',[1 1 1]*(1-0.05*i));
    hold on;
end
hold on;
for i = 1:5
    scatter(Results.Fig_AlphaPrctl.PanelA.dx(i), Results.Fig_AlphaPrctl.PanelA.dy(i), 'filled', 'dk');
end

lbls = {'CAPM','FF3','FF4','FF5','FF6',Results.Text.signalChar};
leg=legend(lbls, 'Location', 'northwest', 'box', 'off');
leg.ItemTokenSize = [60, 50];
ylabel({'Gross Alpha (%/month)'});
xlabel('Anomaly percentile rank');
title('Gross Alpha Percentiles');
set(gca,'FontSize',30)
set(gca,'FontName','Times New Roman')

% Plot Panel B: Net
subplot(1,2,2);
for i=1:size(Results.Fig_AlphaPrctl.PanelB.y,2)
    plot(Results.Fig_AlphaPrctl.PanelB.x, Results.Fig_AlphaPrctl.PanelB.y(:,i),'LineWidth',4.5,'color',[1 1 1]*(1-0.05*i));
    hold on;
end
hold on;
for i = 1:5
    scatter(Results.Fig_AlphaPrctl.PanelB.dx(i), Results.Fig_AlphaPrctl.PanelB.dy(i), 'filled', 'dk');
end

ylabel({'Novy-Marx and Velikov  (RFS, 2016)';'Net Generalized Alpha (%/month)'});
xlabel('Anomaly percentile rank');
title('Net Alpha Percentiles');
set(gca,'FontSize',30)
set(gca,'FontName','Times New Roman')
exportgraphics(h,[filePath, Results.Text.signalChar, '_figureAlphaPrctl.pdf'],'ContentType','vector')    

% Include Figure 3 in the latex document
fprintf(fid, ['\\begin{landscape}' '\n']);
fprintf(fid, ['\\begin{figure}[!htbp]' '\n']);
fprintf(fid, ['\\begin{center}' '\n']);
fprintf(fid, ['\\hspace{-4mm} \\includegraphics[width=\\linewidth,keepaspectratio]{', Results.Text.signalChar, '_figureAlphaPrctl}' '\n']);
fprintf(fid, ['\\end{center}' '\n']);
fprintf(fid, ['\\caption{Gross and generalized net alpha percentiles of anomalies relative to factor models \\\\' '\n']);
fprintf(fid, ['\\small{This figure plots the percentile ranks for ', Results.Text.nAnoms, ...
              ' anomaly trading strategies in terms of alphas (solid lines), and compares those with the ', Results.Text.signalChar, ...
              ' trading strategy alphas (diamonds). The strategies are constructed using value-weighted ', ...
              'quintile sorts using NYSE breakpoints. The alphas include those with respect to the CAPM,  ', ...
              '\\citet{FamaFrench1993} three-factor model, \\citet{FamaFrench1993} three-factor model augmented with the ', ...
              '\\citet{Carhart1997} momentum factor, \\citet{FamaFrench2015} five-factor model, and ', ...
              'the \\citet{FamaFrench2015} five-factor model augmented with the \\citet{Carhart1997} momentum factor ', ...
              'following \\citet{FamaFrench2018}. ', ...
              'The left panel plots alphas with no adjustment for trading costs. ', ...
              'The right panel plots \\citet{Novy-MarxVelikov2016} net generalized alphas.}' '\n']);
fprintf(fid, ['\\label{fig:factorModelAlphas}}' '\n']);
fprintf(fid, ['\\end{figure}' '\n\n\n']);
fprintf(fid, ['\\end{landscape}' '\n']);

